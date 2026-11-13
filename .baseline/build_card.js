#!/usr/bin/env node
/* build_card.js: the link-preview card builder (baseline 1.9.0 and later; the dithering limit and the background
   check from 1.9.2; the centred layout, the Teams crop and the version label from 1.10.0; the optional metal
   wordmark from 1.11.5; the favicon.ico and the --icons-only mode from 1.12.2).

   From 1 data file and 1 approved illustration per site it renders, in headless Chromium with the bundled Inter
   fonts (card-fonts/, SIL OFL 1.1, never served):
     <site>-card.png        the 1200 by 630 link-preview image, reduced to 256 colours (median cut, Floyd-Steinberg)
     <site>-card-safe.png   the same render with the layout's safe area outlined in red dots and the Microsoft Teams
                            crop in cyan dashes; for review, never served
     <site>-card-teams.png  the part of the card Teams shows (x 208 to 992, 784 by 630); for review, never served
     <site>-touch.png       the 180 by 180 Apple touch icon (the logo at 144 px, centred on the site's light --bg,
                            opaque), when the data file names a logo; from 1.12.2 a PNG logo of at most 180 by 180
                            px is placed unscaled at the centre instead, its transparent pixels showing the --bg
     <site>-favicon.ico     from 1.12.2 (owner, 2026-11-09, D-080), when the data file names a favicon: 3 frames, 16,
                            32 and 48 px, 32-bit RGBA stored as PNG, served by the site as /favicon.ico. From the
                            site's <site>-favicon.svg each frame is rendered at its own size in the same headless
                            Chromium, so no frame is a downscale; from a PNG (a site whose logo is photographic
                            artwork, with no SVG favicon: vendorreplies.ai) the visible pixels are centred on a
                            transparent square and downscaled (Lanczos, as Pillow resizes), and the 32 and 16 px
                            frames are also written as <site>-favicon-32.png and <site>-favicon-16.png
     card-tags.html         the Open Graph and Twitter tags for the page head
     cardpreview.html       the before and after review page (noindex, no inline style or script, so it is
                            allowed under the family's CSP), with the before image and its Teams crop
                            (<site>-card-before.png, <site>-card-before-teams.png) when --before is given
     card-report.txt        every measured size, clearance and contrast ratio, the checks, and the SHA-256 of
                            every input and every file written

   2 layouts, chosen by the data file's layout field (owner, 2026-11-05: an option, with the Teams crop reported).
   layout = "side" (the default) is the round-2 family layout the owner approved on 2026-10-31: the illustration 430 px high,
   right-aligned in a 340 px box, a 28 px gap, so the text column is 592 px wide; the wordmark fitted to the
   column in whole pixels (cap 112, floor 60), weight 800, the name in the site colour and the TLD in gold
   #fbbf24 over a 6 px gold rule; both statement lines at 1 shared size (each fitted to the column, cap 48, floor
   20, the smaller applies), weight 700; the subline at 27 px, white at 88 %, balanced wrapping, or with
   sub_nowrap on 1 line fitted to the column (cap 30, floor 18); an optional formula row fitted to 960 px (cap 40,
   floor 20). A text that cannot fit at its floor is a failure, never a smaller font.
   layout = "centre" keeps every glyph and the illustration inside x 248 to 952, 40 px inside the area Microsoft Teams
   shows (x 208 to 992: Teams keeps the full height and the centre 784 px of the width, measured 2026-11-05 from 1
   Teams preview, which showed x 206 to 990, within 2 px of centred). It stacks, centred in a 704 by 530 safe area at
   x 248, y 50: the illustration (square, 250 px high at most, shrunk to fit the text below it, never under 140 px),
   an 18 px gap, the wordmark fitted to 704 px (cap 88, floor 60) over its gold rule, both statement lines at 1
   shared size (cap 34, floor 20), the subline at 27 px balanced and centred (or with sub_nowrap fitted to 704 px,
   cap 30, floor 18), and the optional formula row fitted to 704 px (cap 40, floor 20). Colours, weights and
   letter-spacing are those of the side layout.
   From 1.11.5 (owner, 2026-11-07, D-054), 1 optional field, off by default, which leaves the page and every output
   as in 1.11.4: word_style = "metal" (centred layout only) sets the wordmark's name in a platinum gradient and its
   TLD and rule in a gold gradient (the posluns.ca series v6 gradients).

   Checks (any failure exits 1 and writes no card): every required field present and well formed; the
   illustration and logo SVGs hold no script, event attribute, javascript: URL, external reference, style,
   foreignObject or DOCTYPE; every character is in the cmap of each bundled Inter file; every text fits at or above its floor
   and inside the layout's safe area (clearance from the glyph boxes: side 120 px left and right, centre 248 px; top and
   bottom side 75 px, centre 50 px); side: at least 28 px between the text column and the illustration; centre: the illustration at
   least 140 px high and at least 18 px above the text; contrast against the brightest background pixel
   under each text box, the text hidden (statement lines and subline 4.5:1, wordmark and formula row 3:1 as
   large text); the output exactly 1200 by 630; 2 renders of the same inputs give the same pixels; and, from 1.9.2,
   outside the safe area no pixel of the 256-colour card differs from the full-colour render by more than
   MARGIN_MAX levels in any channel (the background check, after auditthis.ai's report of stray pixels in 1.9.0).
   With the metal wordmark (from 1.11.5) each gradient fill is measured at its worst stop. From 1.12.2 the favicon
   SVG is checked as the logo is, and a PNG logo or favicon must be a well-formed 8-bit RGBA or RGB PNG, not
   interlaced and without a tRNS chunk (a transparent colour, which the builder would not apply), of the sizes given under the data-file keys below; each favicon frame is exactly its size and holds
   at least 1 visible pixel.
   The Teams crop is measured for both layouts and reported (the clearance of the content inside x 208 to 992, and
   what lies outside it); with the centre layout the safe area keeps the content inside it, and with the side layout
   it is a finding for the owner's review, never a failure.

   Usage:
     node build_card.js --data <site-card.toml> --out <folder> [--before <png>] [--palettes <palettes.css>]
     node build_card.js --data <site-card.toml> --out <folder> --icons-only [--palettes <palettes.css>]
   --icons-only  from 1.12.2: writes only the icons (<site>-touch.png, <site>-favicon.ico and, from a PNG favicon,
              its 2 PNG frames) and card-report.txt, and no card; the data file then needs only site and a logo or a
              favicon (the card fields may stay in it and are not read), so a site without a card, or one that keeps
              its own card (vendorreplies.ai), builds its icons with the same tool
   Data-file keys for the icons (from 1.12.2; each path relative to the data file, each file checked and listed with
   its SHA-256 under the report's Inputs):
     logo     the full-colour logo: an SVG (as before), or a PNG of at most 180 by 180 px, 8-bit RGBA or RGB
     favicon  the site's favicon: <site>-favicon.svg (no script, style or external reference, as the logo), or a
              PNG, 8-bit RGBA or RGB, whose visible pixels span at least 48 px, so no frame is enlarged
   The icon PNGs (the .ico frames, the PNG favicons and a PNG logo's touch icon) are encoded as Pillow 12.1.1 encodes
   them (per row the filter with the lowest sum of absolute differences, zlib level 6, or 9 for the touch icon, with
   the filtered strategy), so with the same inputs, Chromium pixels and zlib they equal byte for byte the files
   1.12.1 shipped in logos/, made by tools/build_icons.py; the report's Icons block records the Node.js and zlib
   versions, which every icon PNG goes through. A touch icon from an SVG logo is written as before.
   --before   the card the site serves today, shown as "before" in cardpreview.html: a PNG of any size in the exact
              proportion 1200:630. The file is checked in this order, and the first check it fails exits 1 with 1
              message, before the image is decoded, a browser is launched or a file is written: (1) it starts with
              the full 8-byte PNG signature; (2) it is at least 24 bytes long; (3) bytes 12 to 15 name the IHDR
              chunk (1 to 3 from 1.11.3); (4) the IHDR length field, bytes 8 to 11, equals 13 (from 1.11.4); (5) the
              IHDR width and height, in integers, are w and h greater than 0 with w * 630 === h * 1200 (from 1.11.3;
              600 by 315 and 2400 by 1260 pass, 1200 by 628 and 0 by 0 fail)
   --palettes the baseline's palettes.css, for the touch icon's light --bg (default: the package's own,
              ../palettes.css); a data file may set touch_bg instead
   Needs Node.js 18 or later and the playwright package with its full Chromium build (npx playwright install
   chromium): from 1.11.2 the builder resolves chromium.executablePath() once, launches both browsers with
   exactly that executable, and refuses a headless-shell build, whose text edges differ, before rendering.
   Nothing is fetched: every request the page makes is refused, and the fonts, illustration, logo and favicon are
   read from disk. With --icons-only and no SVG input no browser is launched.
   Exit status: 0 when every check passes and every file is written; 1 when any check fails or an input cannot
   be read; 2 for a usage error. Repeatable on 1 machine: the same inputs and the same Chromium build give the
   same SHA-256; another Chromium build may draw text edges differently, so the report records the build (the
   launched executable's name: chrome on Linux, chrome.exe on Windows, Google Chrome for Testing on macOS)
   next to the version. */
"use strict";
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const crypto = require("crypto");

// The package version this builder belongs to; the report and the tags name it. The release checks fail when it
// differs from the package's version.
const VERSION = "1.13.0";
const W = 1200, H = 630, SAFE = { l: 120, t: 75, w: 960, h: 480 };
const ART = 430, ART_BOX = 340, GAP = 28, COL = SAFE.w - ART_BOX - GAP;
// The centred layout (from 1.10.0) and the Microsoft Teams crop it keeps clear of.
const TEAMS = { l: 208, r: 992 }, CSAFE = { l: 248, t: 50, w: 704, h: 530 };
const C_ART_MAX = 250, C_ART_MIN = 140, C_GAP = 18;
const GOLD = "#fbbf24", BLUE = "#5eb0ef";
const FONT_FILES = [["Inter-Regular.otf", 400], ["Inter-Bold.otf", 700], ["Inter-ExtraBold.otf", 800]];
// From 1.11.5 (owner, 2026-11-07, D-054): the optional metal wordmark, off by default. The gradients of the
// posluns.ca series v6 cards (scripts/drafts/cards/build_cards.py: GOLD_GRAD, PLAT_GRAD), with their stops for the
// contrast check. In each gradient every channel moves in 1 direction between 2 stops, so the darkest and the
// lightest colours are stops; the check takes the worst stop.
const GOLD_STOPS = ["#fff1b8", "#f6cf55", "#e0a521", "#fbdc7a"], PLAT_STOPS = ["#ffffff", "#e6e9ee", "#b9c0c9", "#f1f3f6"];
const grad = (stops, at) => `linear-gradient(180deg, ${stops.map((c, i) => `${c} ${at[i]}%`).join(", ")})`;
const GOLD_GRAD = grad(GOLD_STOPS, [0, 38, 62, 100]), PLAT_GRAD = grad(PLAT_STOPS, [0, 40, 62, 100]);

class Fail extends Error {}
function usage(msg) {
  if (msg) { console.error("usage error: " + msg); }
  console.error("usage: node build_card.js --data <site-card.toml> --out <folder> [--before <png>] [--palettes <palettes.css>]");
  console.error("       node build_card.js --data <site-card.toml> --out <folder> --icons-only [--palettes <palettes.css>]");
  process.exit(2);
}
const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");
const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// ---------------------------------------------------------------- data file: a small TOML subset
// key = "string" (with \" \\ \n \t \uXXXX escapes), key = true | false, key = integer; # comments; no tables.
function parseToml(text, file) {
  const out = {};
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.replace(/^\s+|\s+$/g, "");
    if (!line || line.startsWith("#")) { return; }
    const m = line.match(/^([A-Za-z0-9_]+)\s*=\s*(.*)$/);
    if (!m) { throw new Fail(`${file}:${i + 1}: expected key = value`); }
    const [, key, rest] = m;
    if (key in out) { throw new Fail(`${file}:${i + 1}: ${key} is set twice`); }
    let v, tail;
    if (rest.startsWith('"')) {
      let j = 1, s = "";
      for (; j < rest.length && rest[j] !== '"'; j++) {
        if (rest[j] === "\\") {
          const c = rest[++j];
          if (c === "n") { s += "\n"; } else if (c === "t") { s += "\t"; } else if (c === '"' || c === "\\") { s += c; }
          else if (c === "u" && /^[0-9a-fA-F]{4}$/.test(rest.slice(j + 1, j + 5))) { s += String.fromCharCode(parseInt(rest.slice(j + 1, j + 5), 16)); j += 4; }
          else { throw new Fail(`${file}:${i + 1}: unsupported escape \\${c}`); }
        } else { s += rest[j]; }
      }
      if (j >= rest.length) { throw new Fail(`${file}:${i + 1}: unterminated string`); }
      v = s; tail = rest.slice(j + 1);
    } else {
      const t = rest.match(/^(true|false|-?\d+)(.*)$/);
      if (!t) { throw new Fail(`${file}:${i + 1}: ${key}: a value is a "string", true, false or an integer`); }
      v = t[1] === "true" ? true : t[1] === "false" ? false : parseInt(t[1], 10); tail = t[2];
    }
    if (tail.trim() && !tail.trim().startsWith("#")) { throw new Fail(`${file}:${i + 1}: text after the value`); }
    out[key] = v;
  });
  return out;
}

const FIELDS = {
  site: "the template's site id, lowercase letters, digits and hyphens", name: "the wordmark name", tld: "the wordmark's TLD (default .ai)",
  line1: "statement line 1", line2: "statement line 2", sub: "the subline", sub_nowrap: "true keeps the subline on 1 line",
  formula: "optional formula row; {gold} and [blue] spans", layout: "optional: side (the default) or centre", art: "the approved illustration SVG, relative to the data file",
  logo: "optional: the site's full-colour logo, for the touch icon: an SVG, or (from 1.12.2) a PNG of at most 180 by 180 px", word_colour: "the wordmark name's colour, #rrggbb",
  background: "the card background, CSS gradients and colours only", touch_bg: "optional: the touch icon's background, #rrggbb",
  site_name: "optional: the site name in the tags (default name + tld)", domain: "optional (default: name + tld, lowercase)",
  title: "optional og:title", description: "optional og:description", alt: "optional og:image:alt",
  word_style: "optional (from 1.11.5): flat (the default) or metal, the name in a platinum gradient and the TLD and rule in a gold gradient; layout = \"centre\" only",
  favicon: "optional (from 1.12.2): the site's favicon, <site>-favicon.svg or a PNG, for <site>-favicon.ico",
};
// The icon fields (from 1.12.2): the paths of the logo and the favicon, each an SVG or a PNG, and touch_bg.
function readIconFields(d, file, dir) {
  for (const k of ["logo", "favicon", "touch_bg"]) {
    if (k in d && (typeof d[k] !== "string" || !d[k].trim())) { throw new Fail(`${file}: ${k} must be a non-empty string (${FIELDS[k]})`); }
  }
  for (const k of ["logo", "favicon"]) {
    if (k in d && !/\.(svg|png)$/i.test(d[k])) { throw new Fail(`${file}: ${k} must name an .svg or a .png file (${FIELDS[k]})`); }
  }
  if (d.touch_bg && !/^#[0-9a-fA-F]{6}$/.test(d.touch_bg)) { throw new Fail(`${file}: touch_bg must be #rrggbb`); }
  d.logoPath = d.logo ? path.resolve(dir, d.logo) : null;
  d.faviconPath = d.favicon ? path.resolve(dir, d.favicon) : null;
}
function readData(file, iconsOnly = false) {
  let text;
  try { text = fs.readFileSync(file, "utf8"); } catch (e) { throw new Fail(`cannot read ${file}: ${e.message}`); }
  const d = parseToml(text, file);
  for (const k of Object.keys(d)) { if (!(k in FIELDS)) { throw new Fail(`${file}: unknown field ${k}`); } }
  if (iconsOnly) { // from 1.12.2: only the site id and the icon fields are read
    if (typeof d.site !== "string" || !/^[a-z0-9-]+$/.test(d.site)) { throw new Fail(`${file}: site is required (${FIELDS.site})`); }
    readIconFields(d, file, path.dirname(path.resolve(file)));
    if (!d.logoPath && !d.faviconPath) { throw new Fail(`${file}: --icons-only needs a logo or a favicon in the data file`); }
    return d;
  }
  for (const k of ["site", "name", "line1", "line2", "sub", "art", "word_colour", "background"]) {
    if (typeof d[k] !== "string" || !d[k].trim()) { throw new Fail(`${file}: ${k} is required (${FIELDS[k]})`); }
  }
  for (const k of ["tld", "formula", "layout", "site_name", "domain", "title", "description", "alt"]) {
    if (k in d && typeof d[k] !== "string") { throw new Fail(`${file}: ${k} must be a string`); }
  }
  if ("sub_nowrap" in d && typeof d.sub_nowrap !== "boolean") { throw new Fail(`${file}: sub_nowrap must be true or false`); }
  if ("word_style" in d && d.word_style !== "flat" && d.word_style !== "metal") { throw new Fail(`${file}: word_style must be "flat" or "metal"`); }
  d.layout = d.layout || "side";
  if (d.layout !== "side" && d.layout !== "centre") { throw new Fail(`${file}: layout must be "side" or "centre"`); }
  if (d.word_style === "metal" && d.layout !== "centre") { throw new Fail(`${file}: word_style = "metal" needs layout = "centre"`); }
  if (!/^[a-z0-9-]+$/.test(d.site)) { throw new Fail(`${file}: site: ${FIELDS.site}`); }
  if (!/^#[0-9a-fA-F]{6}$/.test(d.word_colour)) { throw new Fail(`${file}: word_colour must be #rrggbb`); }
  if (!/^[a-zA-Z0-9#(),.%\s-]+$/.test(d.background) || /url\s*\(|expression|var\s*\(/i.test(d.background)) {
    throw new Fail(`${file}: background may hold only CSS gradients, colours, lengths and percentages`);
  }
  const dir = path.dirname(path.resolve(file));
  readIconFields(d, file, dir);
  d.tld = d.tld || ".ai";
  d.site_name = d.site_name || d.name + d.tld;
  d.domain = d.domain || (d.name + d.tld).toLowerCase();
  if (!/^[a-z0-9.-]+$/.test(d.domain)) { throw new Fail(`${file}: domain must be a host name`); }
  d.title = d.title || `${d.site_name} - ${d.line1.replace(/\.$/, "")}`;
  d.description = d.description || d.sub;
  d.alt = d.alt || `${d.site_name}: ${d.line1} ${d.line2}`;
  d.artPath = path.resolve(dir, d.art);
  return d;
}

// ---------------------------------------------------------------- SVG input checks
function checkSvg(file, label) {
  let s;
  try { s = fs.readFileSync(file, "utf8"); } catch (e) { throw new Fail(`cannot read the ${label} ${file}: ${e.message}`); }
  const bad = [];
  if (!/<svg[\s>]/i.test(s)) { bad.push("no <svg> element"); }
  if (/<script/i.test(s)) { bad.push("a <script> element"); }
  if (/\son[a-z]+\s*=/i.test(s)) { bad.push("an event attribute (on...=)"); }
  if (/javascript:/i.test(s)) { bad.push("a javascript: URL"); }
  if (/<foreignObject/i.test(s)) { bad.push("a <foreignObject> element"); }
  if (/<!DOCTYPE|<!ENTITY/i.test(s)) { bad.push("a DOCTYPE or ENTITY declaration"); }
  if (/<style[\s>]/i.test(s) || /\sstyle\s*=/i.test(s)) { bad.push("inline style"); }
  for (const m of s.matchAll(/(?:\s(?:xlink:)?href|\ssrc)\s*=\s*["']([^"']*)["']/gi)) { if (!m[1].startsWith("#")) { bad.push(`an external reference (${m[1].slice(0, 40)})`); } }
  for (const m of s.matchAll(/url\(\s*["']?([^)"']*)/gi)) { if (!m[1].startsWith("#")) { bad.push(`an external url() (${m[1].slice(0, 40)})`); } }
  if (/<image[\s>]/i.test(s)) { bad.push("an <image> element"); }
  if (bad.length) { throw new Fail(`the ${label} ${file} holds ${[...new Set(bad)].join(", ")}`); }
  return Buffer.from(s, "utf8");
}

// ---------------------------------------------------------------- PNG: decode (8-bit RGB or RGBA) and encode
function crcTable() { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) { c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; } t[n] = c >>> 0; } return t; }
const CRC = crcTable();
function crc32(buf) { let c = 0xffffffff; for (let i = 0; i < buf.length; i++) { c = CRC[(c ^ buf[i]) & 0xff] ^ (c >>> 8); } return (c ^ 0xffffffff) >>> 0; }
function decodePng(buf, channels = 3) { // channels 4 (from 1.12.2): RGBA, alpha 255 where the PNG has none
  if (buf.readUInt32BE(0) !== 0x89504e47) { throw new Fail("not a PNG"); }
  let p = 8, w = 0, h = 0, depth = 0, ctype = 0, inter = 0, plte = null; const idat = [];
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString("ascii", p + 4, p + 8), data = buf.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") { w = data.readUInt32BE(0); h = data.readUInt32BE(4); depth = data[8]; ctype = data[9]; inter = data[12]; }
    else if (type === "IDAT") { idat.push(data); } else if (type === "PLTE") { plte = data; } else if (type === "IEND") { break; }
    p += 12 + len;
  }
  if (depth !== 8 || (ctype !== 2 && ctype !== 6 && !(ctype === 3 && plte)) || inter) { throw new Fail(`unsupported PNG (depth ${depth}, colour type ${ctype}, interlace ${inter})`); }
  const bpp = ctype === 6 ? 4 : ctype === 3 ? 1 : 3, stride = w * bpp, raw = zlib.inflateSync(Buffer.concat(idat));
  const n = channels, out = new Uint8Array(w * h * n), prev = new Uint8Array(stride), cur = new Uint8Array(stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? cur[x - bpp] : 0, b = prev[x], c = x >= bpp ? prev[x - bpp] : 0;
      let v = line[x];
      if (f === 1) { v += a; } else if (f === 2) { v += b; } else if (f === 3) { v += (a + b) >> 1; }
      else if (f === 4) { const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      cur[x] = v & 0xff;
    }
    for (let x = 0; x < w; x++) {
      const o = (y * w + x) * n;
      if (n === 4) { out[o + 3] = ctype === 6 ? cur[x * 4 + 3] : 255; }
      if (ctype === 3) { const k = cur[x] * 3; out[o] = plte[k]; out[o + 1] = plte[k + 1]; out[o + 2] = plte[k + 2]; continue; }
      out[o] = cur[x * bpp]; out[o + 1] = cur[x * bpp + 1]; out[o + 2] = cur[x * bpp + 2];
    }
    prev.set(cur);
  }
  return { w, h, px: out };
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, "ascii"), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, c]);
}
function encodePng(w, h, rows, ctype, palette) { // rows: Buffer of h * (1 + w * bpp), filter bytes included
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = ctype;
  const parts = [Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr)];
  if (palette) { parts.push(chunk("PLTE", Buffer.from(palette))); }
  parts.push(chunk("IDAT", zlib.deflateSync(rows, { level: 9 })), chunk("IEND", Buffer.alloc(0)));
  return Buffer.concat(parts);
}
function rgbPng(img) {
  const rows = Buffer.alloc(img.h * (1 + img.w * 3));
  for (let y = 0; y < img.h; y++) { Buffer.from(img.px.buffer, img.px.byteOffset + y * img.w * 3, img.w * 3).copy(rows, y * (1 + img.w * 3) + 1); }
  return encodePng(img.w, img.h, rows, 2, null);
}

// ---------------------------------------------------------------- icons (from 1.12.2; owner, 2026-11-09, D-080)
// The site's favicon.ico and, from a PNG logo, its touch icon. The PNGs inside are encoded as Pillow 12.1.1 encodes
// them, the encoder of 1.12.1's tools/build_icons.py, so that the builder reproduces the files 1.12.1 shipped in
// logos/: per row the filter (none, up, sub, then average when optimizing, then Paeth; a later one only when its sum
// is lower) with the lowest sum of absolute signed bytes, and zlib level 6, or 9 when optimizing, memLevel 9, with
// the filtered strategy.
const ICO_SIZES = [16, 32, 48], TOUCH = 180, FAV_MIN = 48, PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
function pillowPng(w, h, px, bpp, optimize = false) { // px: w * h * bpp bytes, RGBA (bpp 4) or RGB (bpp 3)
  const st = w * bpp, rows = Buffer.alloc(h * (st + 1)), order = optimize ? [0, 2, 1, 3, 4] : [0, 2, 1, 4];
  let prev = new Uint8Array(st);
  for (let y = 0; y < h; y++) {
    const cur = px.subarray(y * st, (y + 1) * st);
    let best = null, bestType = 0, sum = Infinity;
    for (const t of order) {
      if (sum === 0) { break; }
      const f = Buffer.alloc(st); let s = 0;
      for (let x = 0; x < st; x++) {
        const a = x >= bpp ? cur[x - bpp] : 0, b = prev[x], c = x >= bpp ? prev[x - bpp] : 0;
        let p = 0;
        if (t === 1) { p = a; } else if (t === 2) { p = b; } else if (t === 3) { p = (a + b) >> 1; }
        else if (t === 4) { const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c); p = pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
        const v = (cur[x] - p) & 0xff; f[x] = v; s += v < 128 ? v : 256 - v;
      }
      if (s < sum) { sum = s; best = f; bestType = t; }
    }
    rows[y * (st + 1)] = bestType; best.copy(rows, y * (st + 1) + 1);
    prev = cur;
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = bpp === 4 ? 6 : 2;
  const z = zlib.deflateSync(rows, { level: optimize ? 9 : 6, memLevel: 9, strategy: zlib.constants.Z_FILTERED });
  return Buffer.concat([PNG_SIG, chunk("IHDR", ihdr), chunk("IDAT", z), chunk("IEND", Buffer.alloc(0))]);
}
// An ICO of PNG frames (ICONDIR type 1; each entry: width, height, 0 colours, 0 reserved, 0 planes, 32 bits per
// pixel, the PNG's length and offset), the frames in the order given, as Pillow writes it.
function icoFile(frames) { // frames: [{ n, px }] with px n * n * 4 RGBA bytes
  const pngs = frames.map((f) => pillowPng(f.n, f.n, f.px, 4));
  const head = Buffer.alloc(6 + 16 * frames.length); head.writeUInt16LE(1, 2); head.writeUInt16LE(frames.length, 4);
  let off = head.length;
  frames.forEach((f, i) => {
    const e = 6 + 16 * i; head[e] = f.n < 256 ? f.n : 0; head[e + 1] = f.n < 256 ? f.n : 0; head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(pngs[i].length, e + 8); head.writeUInt32LE(off, e + 12); off += pngs[i].length;
  });
  return { ico: Buffer.concat([head, ...pngs]), pngs };
}
// A PNG logo or favicon: the full signature, an IHDR of length 13, 8-bit RGBA or RGB, not interlaced, no tRNS chunk;
// read as RGBA.
function readPngInput(file, label) {
  let b; try { b = fs.readFileSync(file); } catch (e) { throw new Fail(`cannot read the ${label} ${file}: ${e.message}`); }
  if (b.length < 33 || !b.subarray(0, 8).equals(PNG_SIG) || b.readUInt32BE(8) !== 13 || b.toString("ascii", 12, 16) !== "IHDR") { throw new Fail(`the ${label} ${file} is not a valid PNG`); }
  if (b[24] !== 8 || (b[25] !== 2 && b[25] !== 6) || b[28] !== 0) { throw new Fail(`the ${label} ${file} must be an 8-bit RGBA or RGB PNG, not interlaced (depth ${b[24]}, colour type ${b[25]}, interlace ${b[28]})`); }
  // A tRNS chunk (a transparent colour) is refused: decodePng ignores it, so its pixels would come out opaque.
  for (let p = 8; p + 8 <= b.length;) {
    const len = b.readUInt32BE(p), type = b.toString("ascii", p + 4, p + 8);
    if (type === "tRNS") { throw new Fail(`the ${label} ${file} carries a tRNS chunk (a transparent colour), which the builder does not apply; save it as 8-bit RGBA with an alpha channel`); }
    if (type === "IEND") { break; }
    p += 12 + len;
  }
  let img; try { img = decodePng(b, 4); } catch (e) { throw new Fail(`the ${label} ${file} cannot be decoded: ${e.message}`); }
  if (!img.w || !img.h || img.px.length !== img.w * img.h * 4) { throw new Fail(`the ${label} ${file} cannot be decoded`); }
  return { buf: b, img };
}
// Pillow's Image.paste(src, box, src) of RGBA onto RGBA: every channel, alpha included, blended by the source alpha.
const div255 = (a) => { const t = a + 128; return ((t >> 8) + t) >> 8; };
function pasteRgba(dst, dw, src, sw, sh, ox, oy) {
  for (let y = 0; y < sh; y++) {
    for (let x = 0; x < sw; x++) {
      const s = (y * sw + x) * 4, t = ((y + oy) * dw + x + ox) * 4, m = src[s + 3];
      for (let c = 0; c < 4; c++) { dst[t + c] = div255(dst[t + c] * (255 - m) + src[s + c] * m); }
    }
  }
}
// Pillow's LANCZOS resize of an RGBA square (Resample.c): premultiplied alpha, a horizontal then a vertical pass of
// 3-lobe Lanczos weights in 22-bit fixed point, then the alpha divided out again.
const PB = 22;
function lanczosCoeffs(inSize, outSize) {
  const sinc = (x) => { if (x === 0) { return 1; } x *= Math.PI; return Math.sin(x) / x; };
  const filter = (x) => (x >= -3 && x < 3 ? sinc(x) * sinc(x / 3) : 0);
  const scale = inSize / outSize, fscale = Math.max(scale, 1), support = 3 * fscale, ss = 1 / fscale, out = [];
  for (let xx = 0; xx < outSize; xx++) {
    const centre = (xx + 0.5) * scale;
    const xmin = Math.max(0, Math.trunc(centre - support + 0.5)), xmax = Math.min(inSize, Math.trunc(centre + support + 0.5)) - xmin;
    const w = []; let ww = 0;
    for (let x = 0; x < xmax; x++) { const v = filter((x + xmin - centre + 0.5) * ss); w.push(v); ww += v; }
    out.push({ xmin, k: w.map((v) => { const q = ww !== 0 ? v / ww : v; return q < 0 ? Math.trunc(-0.5 + q * (1 << PB)) : Math.trunc(0.5 + q * (1 << PB)); }) });
  }
  return out;
}
function lanczosSquare(src, size, n) {
  const clip8 = (v) => (v >= 2 ** (PB + 8) ? 255 : v <= 0 ? 0 : Math.floor(v / 2 ** PB));
  const pre = new Uint8Array(src.length);
  for (let i = 0; i < src.length; i += 4) { const a = src[i + 3]; for (let c = 0; c < 3; c++) { const t = src[i + c] * a + 128; pre[i + c] = ((t >> 8) + t) >> 8; } pre[i + 3] = a; }
  const kk = lanczosCoeffs(size, n), y0 = kk[0].xmin, th = kk[n - 1].xmin + kk[n - 1].k.length - y0;
  const tmp = new Uint8Array(n * th * 4), out = new Uint8Array(n * n * 4);
  for (let y = 0; y < th; y++) {
    for (let x = 0; x < n; x++) { const { xmin, k } = kk[x]; for (let c = 0; c < 4; c++) { let s = 1 << (PB - 1); for (let j = 0; j < k.length; j++) { s += pre[((y + y0) * size + xmin + j) * 4 + c] * k[j]; } tmp[(y * n + x) * 4 + c] = clip8(s); } }
  }
  for (let y = 0; y < n; y++) {
    const { xmin, k } = kk[y];
    for (let x = 0; x < n; x++) { for (let c = 0; c < 4; c++) { let s = 1 << (PB - 1); for (let j = 0; j < k.length; j++) { s += tmp[((xmin + j - y0) * n + x) * 4 + c] * k[j]; } out[(y * n + x) * 4 + c] = clip8(s); } }
  }
  for (let i = 0; i < out.length; i += 4) { const a = out[i + 3]; if (a !== 0 && a !== 255) { for (let c = 0; c < 3; c++) { out[i + c] = Math.min(255, Math.floor((255 * out[i + c]) / a)); } } }
  return out;
}
// The favicon frames from a PNG: its visible pixels (alpha above 0) centred on a transparent square, each frame
// downscaled from that square, as 1.12.1's build_icons.py made vendorreplies.ai's.
function pngFaviconFrames(img, file) {
  let x0 = img.w, y0 = img.h, x1 = 0, y1 = 0;
  for (let y = 0; y < img.h; y++) { for (let x = 0; x < img.w; x++) { if (img.px[(y * img.w + x) * 4 + 3]) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + 1); y1 = Math.max(y1, y + 1); } } }
  if (x1 <= x0) { throw new Fail(`the favicon ${file} has no visible pixel`); }
  const cw = x1 - x0, ch = y1 - y0, sq = Math.max(cw, ch);
  if (sq < FAV_MIN) { throw new Fail(`the favicon ${file} has visible pixels ${cw} by ${ch} px; a PNG favicon needs at least ${FAV_MIN} px, so no frame is enlarged`); }
  const crop = new Uint8Array(cw * ch * 4);
  for (let y = 0; y < ch; y++) { crop.set(img.px.subarray(((y + y0) * img.w + x0) * 4, ((y + y0) * img.w + x1) * 4), y * cw * 4); }
  const square = new Uint8Array(sq * sq * 4);
  pasteRgba(square, sq, crop, cw, ch, (sq - cw) >> 1, (sq - ch) >> 1);
  return ICO_SIZES.map((n) => ({ n, px: lanczosSquare(square, sq, n) }));
}
// The touch icon from a PNG logo of at most 180 by 180 px: unscaled, centred on the background, opaque RGB.
function pngTouch(img, bg, file) {
  if (img.w > TOUCH || img.h > TOUCH) { throw new Fail(`the logo ${file} is ${img.w} by ${img.h} px; a PNG logo is placed unscaled, so it must be at most ${TOUCH} by ${TOUCH} px`); }
  const t = new Uint8Array(TOUCH * TOUCH * 4), [r, g, b] = hexRgb(bg);
  for (let i = 0; i < TOUCH * TOUCH; i++) { t[i * 4] = r; t[i * 4 + 1] = g; t[i * 4 + 2] = b; t[i * 4 + 3] = 255; }
  pasteRgba(t, TOUCH, img.px, img.w, img.h, (TOUCH - img.w) >> 1, (TOUCH - img.h) >> 1);
  const rgb = new Uint8Array(TOUCH * TOUCH * 3);
  for (let i = 0; i < TOUCH * TOUCH; i++) { rgb[i * 3] = t[i * 4]; rgb[i * 3 + 1] = t[i * 4 + 1]; rgb[i * 3 + 2] = t[i * 4 + 2]; }
  return pillowPng(TOUCH, TOUCH, rgb, 3, true);
}
// An SVG favicon frame: the SVG drawn at n by n px on a transparent page in the builder's Chromium, as RGBA.
async function svgFrame(page, svg, n) {
  await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent"><img src="data:image/svg+xml;base64,${svg.toString("base64")}" width="${n}" height="${n}" style="display:block"></body></html>`, { waitUntil: "load" });
  const img = decodePng(await page.screenshot({ type: "png", omitBackground: true, clip: { x: 0, y: 0, width: n, height: n } }), 4);
  if (img.w !== n || img.h !== n) { throw new Fail(`the ${n} px favicon frame rendered at ${img.w} by ${img.h} px`); }
  return { n, px: img.px };
}

// ---------------------------------------------------------------- 256 colours: median cut, Floyd-Steinberg
// From 1.9.2 the dithering is limited: when the error-steered choice lies more than DITHER_LIMIT levels (in any
// channel) from the pixel's own colour, the pixel takes the palette colour nearest its own colour instead, and the
// error passed on is capped at DITHER_LIMIT per channel. The fallback is the nearest palette colour, not a bounded
// one: where the palette holds no colour within DITHER_LIMIT of the pixel, the pixel still lands further away
// (cleanlanguage measured a 42-level difference, 2026-11-07); outside the safe area the background check holds the
// card within MARGIN_MAX of the full-colour render. Without the cap (1.9.0 and 1.9.1), where the palette had no
// colour close to a smooth area on one side, the error carried forward until it reached a distant colour:
// auditthis.ai's card had 13 stray grey and blue pixels at the centre of a gradient.
const DITHER_LIMIT = 24, MARGIN_MAX = 32;
function quantize(img, safe = SAFE) {
  const { w, h, px } = img, hist = new Map();
  for (let i = 0; i < w * h; i++) { const k = (px[i * 3] << 16) | (px[i * 3 + 1] << 8) | px[i * 3 + 2]; hist.set(k, (hist.get(k) || 0) + 1); }
  const colours = [...hist.entries()].sort((a, b) => a[0] - b[0]);
  const ch = (k, c) => (k >> (16 - 8 * c)) & 0xff;
  const boxOf = (list) => {
    const lo = [255, 255, 255], hi = [0, 0, 0]; let n = 0;
    for (const [k, cnt] of list) { for (let c = 0; c < 3; c++) { const v = ch(k, c); if (v < lo[c]) { lo[c] = v; } if (v > hi[c]) { hi[c] = v; } } n += cnt; }
    const range = [0, 1, 2].map((c) => hi[c] - lo[c]); const axis = range.indexOf(Math.max(...range));
    return { list, n, axis, range: range[axis] };
  };
  let boxes = [boxOf(colours)];
  while (boxes.length < 256) {
    let best = -1;
    boxes.forEach((b, i) => { if (b.list.length > 1 && (best < 0 || b.range * b.n > boxes[best].range * boxes[best].n)) { best = i; } });
    if (best < 0) { break; }
    const b = boxes[best], sorted = b.list.slice().sort((x, y) => ch(x[0], b.axis) - ch(y[0], b.axis) || x[0] - y[0]);
    let acc = 0, cut = 1;
    for (let i = 0; i < sorted.length - 1; i++) { acc += sorted[i][1]; if (acc >= b.n / 2) { cut = i + 1; break; } cut = i + 1; }
    boxes.splice(best, 1, boxOf(sorted.slice(0, cut)), boxOf(sorted.slice(cut)));
  }
  const pal = boxes.map((b) => { const s = [0, 0, 0]; for (const [k, cnt] of b.list) { for (let c = 0; c < 3; c++) { s[c] += ch(k, c) * cnt; } } return s.map((v) => Math.round(v / b.n)); });
  const cache = new Map();
  const nearest = (r, g, b) => {
    const k = (r << 16) | (g << 8) | b; const hit = cache.get(k); if (hit !== undefined) { return hit; }
    let bi = 0, bd = Infinity;
    for (let i = 0; i < pal.length; i++) { const d = (pal[i][0] - r) ** 2 + (pal[i][1] - g) ** 2 + (pal[i][2] - b) ** 2; if (d < bd) { bd = d; bi = i; } }
    cache.set(k, bi); return bi;
  };
  const err = new Float32Array(w * h * 3); for (let i = 0; i < px.length; i++) { err[i] = px[i]; }
  const rows = Buffer.alloc(h * (1 + w));
  let marginDev = 0;
  const clamp = (v) => (v < 0 ? 0 : v > 255 ? 255 : Math.round(v));
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 3, r = clamp(err[i]), g = clamp(err[i + 1]), b = clamp(err[i + 2]);
      let pi = nearest(r, g, b);
      const o = [px[i], px[i + 1], px[i + 2]];
      if (Math.max(Math.abs(pal[pi][0] - o[0]), Math.abs(pal[pi][1] - o[1]), Math.abs(pal[pi][2] - o[2])) > DITHER_LIMIT) { pi = nearest(o[0], o[1], o[2]); }
      rows[y * (1 + w) + 1 + x] = pi;
      const dev = Math.max(Math.abs(pal[pi][0] - o[0]), Math.abs(pal[pi][1] - o[1]), Math.abs(pal[pi][2] - o[2]));
      if ((x < safe.l || x >= safe.l + safe.w || y < safe.t || y >= safe.t + safe.h) && dev > marginDev) { marginDev = dev; }
      const e = [r - pal[pi][0], g - pal[pi][1], b - pal[pi][2]].map((v) => (v > DITHER_LIMIT ? DITHER_LIMIT : v < -DITHER_LIMIT ? -DITHER_LIMIT : v));
      const spread = (dx, dy, f) => { const xx = x + dx, yy = y + dy; if (xx < 0 || xx >= w || yy >= h) { return; } const j = (yy * w + xx) * 3; for (let c = 0; c < 3; c++) { err[j + c] += e[c] * f; } };
      spread(1, 0, 7 / 16); spread(-1, 1, 3 / 16); spread(0, 1, 5 / 16); spread(1, 1, 1 / 16);
    }
  }
  const png = encodePng(w, h, rows, 3, [].concat(...pal));
  png.marginDev = marginDev;
  return png;
}

// ---------------------------------------------------------------- WCAG 2 contrast
const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lum = (p) => 0.2126 * lin(p[0] / 255) + 0.7152 * lin(p[1] / 255) + 0.0722 * lin(p[2] / 255);
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
function worstContrast(img, box, rgb, alpha) { // the brightest background pixel in the box, the text composited over it
  let bright = null, bl = -1;
  for (let y = Math.max(0, Math.floor(box.t)); y <= Math.min(img.h - 1, Math.floor(box.b)); y++) {
    for (let x = Math.max(0, Math.floor(box.l)); x <= Math.min(img.w - 1, Math.floor(box.r)); x++) {
      const i = (y * img.w + x) * 3, p = [img.px[i], img.px[i + 1], img.px[i + 2]], l = lum(p);
      if (l > bl) { bl = l; bright = p; }
    }
  }
  const fg = [0, 1, 2].map((i) => alpha * rgb[i] + (1 - alpha) * bright[i]);
  const a = lum(fg), b = lum(bright);
  return { ratio: Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100, bg: "#" + bright.map((v) => v.toString(16).padStart(2, "0")).join("") };
}

// ---------------------------------------------------------------- the card page (rendered in memory, never written)
function formulaHtml(f) { // {gold} and [blue] spans; everything else plain text
  let out = "", i = 0;
  while (i < f.length) {
    const c = f[i];
    if (c === "{" || c === "[") {
      const close = c === "{" ? "}" : "]", j = f.indexOf(close, i + 1);
      if (j < 0) { throw new Fail(`formula: unclosed ${c}`); }
      out += `<span class="${c === "{" ? "f" : "g"}">${esc(f.slice(i + 1, j))}</span>`; i = j + 1;
    } else { out += esc(c); i++; }
  }
  return out;
}
function cardPage(d, fonts, artUri) {
  const face = fonts.map(([uri, wt]) => `@font-face{font-family:CardInter;src:url(${uri}) format("opentype");font-weight:${wt};font-style:normal}`).join("");
  if (d.layout === "centre") { return cardPageCentre(d, face, artUri); }
  return `<!doctype html><html><head><meta charset="utf-8"><style>${face}
  html,body{margin:0;width:${W}px;height:${H}px;overflow:hidden;font-family:CardInter;color:#fff}
  .card{position:relative;width:${W}px;height:${H}px;background:${d.background}}
  .safe{position:absolute;left:${SAFE.l}px;top:${SAFE.t}px;width:${SAFE.w}px;height:${SAFE.h}px;display:flex;flex-direction:column;justify-content:center;gap:14px}
  .top{display:flex;justify-content:space-between;align-items:center;flex:0 0 auto}
  .text{display:flex;flex-direction:column;justify-content:center;gap:16px;width:${COL}px}
  .artbox{width:${ART_BOX}px;height:${ART}px;display:flex;justify-content:flex-end;align-items:center;flex:none}
  .art{height:${ART}px;max-width:${ART_BOX}px;filter:drop-shadow(0 18px 28px rgba(0,0,0,.45))}
  .brand{margin:0;font-weight:800;line-height:1;letter-spacing:-.03em;text-shadow:0 4px 14px rgba(0,0,0,.4);white-space:nowrap;width:max-content}
  .brand .word{color:${d.word_colour}}
  .brand b{color:${GOLD};font-weight:800}
  .rule{height:6px;border-radius:3px;background:${GOLD};margin:2px 0}
  .line{margin:0;font-weight:700;line-height:1.1;letter-spacing:-.015em;white-space:nowrap;width:max-content;text-shadow:0 2px 8px rgba(0,0,0,.35)}
  .lines{display:flex;flex-direction:column;gap:8px}
  .sub{margin:4px 0 0;font-size:27px;line-height:1.35;font-weight:400;color:rgba(255,255,255,.88);text-wrap:balance}
  .sub.nowrap{white-space:nowrap;width:max-content}
  .formula{margin:0;line-height:1;font-weight:800;letter-spacing:-.01em;white-space:nowrap;width:max-content;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.6)}
  .formula .f{color:${GOLD}}.formula .g{color:${BLUE}}
</style></head><body><div class="card"><div class="safe">
  <div class="top">
    <div class="text">
      <h1 class="brand" id="b"><span class="word">${esc(d.name)}</span><b>${esc(d.tld)}</b></h1>
      <div class="rule" id="r"></div>
      <div class="lines"><p class="line" id="l1">${esc(d.line1)}</p><p class="line" id="l2">${esc(d.line2)}</p></div>
      <p class="sub${d.sub_nowrap ? " nowrap" : ""}" id="s">${esc(d.sub)}</p>
    </div>
    <div class="artbox"><img class="art" src="${artUri}" alt=""></div>
  </div>
  ${d.formula ? `<p class="formula" id="f">${formulaHtml(d.formula)}</p>` : ""}
</div></div></body></html>`;
}
function cardPageCentre(d, face, artUri) { // from 1.10.0: everything stacked and centred inside the Teams crop
  return `<!doctype html><html><head><meta charset="utf-8"><style>${face}
  html,body{margin:0;width:${W}px;height:${H}px;overflow:hidden;font-family:CardInter;color:#fff}
  .card{position:relative;width:${W}px;height:${H}px;background:${d.background}}
  .safe{position:absolute;left:${CSAFE.l}px;top:${CSAFE.t}px;width:${CSAFE.w}px;height:${CSAFE.h}px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:${C_GAP}px}
  .art{width:${C_ART_MAX}px;height:${C_ART_MAX}px;flex:none;filter:drop-shadow(0 18px 28px rgba(0,0,0,.45))}
  .text{display:flex;flex-direction:column;align-items:center;gap:14px;width:${CSAFE.w}px;text-align:center;flex:none}
  .brand{margin:0;font-weight:800;line-height:1;letter-spacing:-.03em;text-shadow:0 4px 14px rgba(0,0,0,.4);white-space:nowrap;width:max-content}
  .brand .word{color:${d.word_colour}}
  .brand b{color:${GOLD};font-weight:800}
  .rule{height:6px;border-radius:3px;background:${GOLD}}
  .line{margin:0;font-weight:700;line-height:1.1;letter-spacing:-.015em;white-space:nowrap;width:max-content;text-shadow:0 2px 8px rgba(0,0,0,.35)}
  .lines{display:flex;flex-direction:column;align-items:center;gap:8px}
  .sub{margin:0;max-width:${CSAFE.w}px;font-size:27px;line-height:1.35;font-weight:400;color:rgba(255,255,255,.88);text-wrap:balance}
  .sub.nowrap{white-space:nowrap;width:max-content;max-width:none}
  .formula{margin:0;line-height:1;font-weight:800;letter-spacing:-.01em;white-space:nowrap;width:max-content;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.6)}
  .formula .f{color:${GOLD}}.formula .g{color:${BLUE}}
${extraCss(d)}</style></head><body><div class="card"><div class="safe">
  <img class="art" src="${artUri}" alt="">
  <div class="text">
    <h1 class="brand" id="b"><span class="word">${esc(d.name)}</span><b>${esc(d.tld)}</b></h1>
    <div class="rule" id="r"></div>
    <div class="lines"><p class="line" id="l1">${esc(d.line1)}</p><p class="line" id="l2">${esc(d.line2)}</p></div>
    <p class="sub${d.sub_nowrap ? " nowrap" : ""}" id="s">${esc(d.sub)}</p>
    ${d.formula ? `<p class="formula" id="f">${formulaHtml(d.formula)}</p>` : ""}
  </div>
</div></div></body></html>`;
}
// From 1.11.5: the CSS of the metal wordmark, "" when it is off, so the page, and every output, is then unchanged.
// The metal wordmark trades text-shadow for filter: drop-shadow, because a text shadow paints over a fill clipped to
// the text.
function extraCss(d) {
  return d.word_style === "metal" ? `  .brand{text-shadow:none;filter:drop-shadow(0 4px 14px rgba(0,0,0,.4))}.brand .word{background:${PLAT_GRAD};-webkit-background-clip:text;background-clip:text;color:transparent}.brand b{background:${GOLD_GRAD};-webkit-background-clip:text;background-clip:text;color:transparent}.rule{background:${GOLD_GRAD}}\n` : "";
}
const FIT = ({ COL, nowrap, centre, C }) => { // runs in the page; the round-2 fitting (side) or the centred fitting, in whole pixels
  if (centre) {
    const width = (el) => el.getBoundingClientRect().width;
    const fit = (el, target, cap, floor) => { let s = cap; el.style.fontSize = s + "px"; while (width(el) > target && s > floor) { s -= 1; el.style.fontSize = s + "px"; } return { size: s, fits: width(el) <= target + 0.01 }; };
    const b = document.getElementById("b"), brand = fit(b, C.w, 88, 60); document.getElementById("r").style.width = width(b) + "px";
    const l1 = document.getElementById("l1"), l2 = document.getElementById("l2"), f1 = fit(l1, C.w, 34, 20), f2 = fit(l2, C.w, 34, 20);
    const ls = Math.min(f1.size, f2.size); l1.style.fontSize = ls + "px"; l2.style.fontSize = ls + "px";
    const f = document.getElementById("f"), formula = f ? fit(f, C.w, 40, 20) : null;
    const sub = nowrap ? fit(document.getElementById("s"), C.w, 30, 18) : null;
    // The illustration takes the height the text leaves: at most C.artMax, never under C.artMin. The text's glyph
    // boxes (a Range over each text, as the checks measure them) reach past its element box, so the gap and the
    // margin below are widened by that overhang: the measured gap is then C.gap and the glyphs stay in the safe area.
    const text = document.querySelector(".text"), tb = text.getBoundingClientRect();
    const glyphs = [...text.querySelectorAll("#b, #l1, #l2, #s, #f")].map((e) => { const g = document.createRange(); g.selectNodeContents(e); return g.getBoundingClientRect(); });
    const over = { t: Math.max(0, tb.top - Math.min(...glyphs.map((r) => r.top))), b: Math.max(0, Math.max(...glyphs.map((r) => r.bottom)) - tb.bottom) };
    const a = Math.min(C.artMax, Math.floor(C.h - tb.height - over.t - over.b - C.gap)), art = document.querySelector(".art");
    art.style.width = Math.max(a, 1) + "px"; art.style.height = Math.max(a, 1) + "px";
    document.querySelector(".safe").style.gap = (C.gap + over.t) + "px"; text.style.marginBottom = over.b + "px";
    return { brand, lines: { size: ls, fits: f1.fits && f2.fits && width(l1) <= C.w + 0.01 && width(l2) <= C.w + 0.01 }, formula, sub, art: { size: a, fits: a >= C.artMin } };
  }
  const width = (el) => el.getBoundingClientRect().width;
  const fit = (el, target, cap, floor) => { let s = cap; el.style.fontSize = s + "px"; while (width(el) > target && s > floor) { s -= 1; el.style.fontSize = s + "px"; } return { size: s, fits: width(el) <= target + 0.01 }; };
  const b = document.getElementById("b"), brand = fit(b, COL, 112, 60); document.getElementById("r").style.width = width(b) + "px";
  const l1 = document.getElementById("l1"), l2 = document.getElementById("l2"), f1 = fit(l1, COL, 48, 20), f2 = fit(l2, COL, 48, 20);
  const ls = Math.min(f1.size, f2.size); l1.style.fontSize = ls + "px"; l2.style.fontSize = ls + "px";
  const f = document.getElementById("f"), formula = f ? fit(f, 960, 40, 20) : null;
  const sub = nowrap ? fit(document.getElementById("s"), COL, 30, 18) : null;
  return { brand, lines: { size: ls, fits: f1.fits && f2.fits && width(l1) <= COL + 0.01 && width(l2) <= COL + 0.01 }, formula, sub, art: null };
};
const MEASURE = () => { // runs in the page; text boxes from a Range over the text (glyph advance boxes)
  const box = (r) => ({ l: r.left, r: r.right, t: r.top, b: r.bottom });
  const txt = (e) => { const g = document.createRange(); g.selectNodeContents(e); return box(g.getBoundingClientRect()); };
  const q = (s) => document.querySelector(s), fs = (s) => parseFloat(getComputedStyle(q(s)).fontSize);
  const m = { brand: txt(q("#b")), rule: box(q("#r").getBoundingClientRect()), l1: txt(q("#l1")), l2: txt(q("#l2")), sub: txt(q("#s")), art: box(q(".art").getBoundingClientRect()) };
  if (q("#f")) { m.formula = txt(q("#f")); }
  // The gap is measured from the text column (wordmark, rule, lines, subline); the formula row runs below the illustration.
  const text = ["brand", "rule", "l1", "l2", "sub"].map((k) => m[k]), all = Object.values(m), s = q("#s");
  return { boxes: m, brandPx: fs("#b"), brandW: m.brand.r - m.brand.l, linePx: fs("#l1"), subPx: fs("#s"), formulaPx: q("#f") ? fs("#f") : null,
    subLines: Math.round(s.getBoundingClientRect().height / (parseFloat(getComputedStyle(s).fontSize) * 1.35)),
    artW: m.art.r - m.art.l, artH: m.art.b - m.art.t,
    clear: { left: Math.min(...all.map((x) => x.l)), right: 1200 - Math.max(...all.map((x) => x.r)), top: Math.min(...all.map((x) => x.t)), bottom: 630 - Math.max(...all.map((x) => x.b)) },
    textRight: Math.max(...text.map((x) => x.r)), gap: m.art.l - Math.max(...text.map((x) => x.r)),
    vgap: Math.min(...text.map((x) => x.t)) - m.art.b,
    span: { l: Math.min(...all.map((x) => x.l)), r: Math.max(...all.map((x) => x.r)) } };
};
function cmapCodepoints(buf) { // the characters a font file maps (cmap format 4 or 12, Windows Unicode)
  const n = buf.readUInt16BE(4); let cmap = -1;
  for (let i = 0; i < n; i++) { if (buf.toString("ascii", 12 + 16 * i, 16 + 16 * i) === "cmap") { cmap = buf.readUInt32BE(20 + 16 * i); } }
  if (cmap < 0) { throw new Fail("a bundled font has no cmap table"); }
  const subs = []; const count = buf.readUInt16BE(cmap + 2);
  for (let i = 0; i < count; i++) { const o = cmap + 4 + 8 * i; subs.push({ pid: buf.readUInt16BE(o), eid: buf.readUInt16BE(o + 2), off: cmap + buf.readUInt32BE(o + 4) }); }
  const pick = subs.find((x) => x.pid === 3 && x.eid === 10 && buf.readUInt16BE(x.off) === 12) || subs.find((x) => x.pid === 3 && x.eid === 1 && buf.readUInt16BE(x.off) === 4);
  if (!pick) { throw new Fail("a bundled font has no Unicode cmap"); }
  const set = new Set(), o = pick.off;
  if (buf.readUInt16BE(o) === 12) {
    const groups = buf.readUInt32BE(o + 12);
    for (let g = 0; g < groups; g++) { const a = buf.readUInt32BE(o + 16 + 12 * g), b = buf.readUInt32BE(o + 20 + 12 * g); for (let c = a; c <= b; c++) { set.add(c); } }
  } else {
    const segs = buf.readUInt16BE(o + 6) / 2, ends = o + 14, starts = ends + 2 * segs + 2, deltas = starts + 2 * segs, ranges = deltas + 2 * segs;
    for (let k = 0; k < segs; k++) {
      const end = buf.readUInt16BE(ends + 2 * k), start = buf.readUInt16BE(starts + 2 * k), delta = buf.readInt16BE(deltas + 2 * k), ro = buf.readUInt16BE(ranges + 2 * k);
      for (let c = start; c <= end && c !== 0xffff; c++) {
        let gid = ro === 0 ? (c + delta) & 0xffff : buf.readUInt16BE(ranges + 2 * k + ro + 2 * (c - start));
        if (ro !== 0 && gid !== 0) { gid = (gid + delta) & 0xffff; }
        if (gid !== 0) { set.add(c); }
      }
    }
  }
  return set;
}

// ---------------------------------------------------------------- outputs
function tagsHtml(d, imgUrl) {
  return [
    `<!-- Link-preview tags for ${d.site_name}, built by build_card.js (baseline ${VERSION}, layout ${d.layout}). The image is ${W} by ${H} px. -->`,
    `<meta property="og:type" content="website">`, `<meta property="og:site_name" content="${esc(d.site_name)}">`,
    `<meta property="og:url" content="https://${d.domain}/">`, `<meta property="og:title" content="${esc(d.title)}">`,
    `<meta property="og:description" content="${esc(d.description)}">`, `<meta property="og:image" content="${imgUrl}">`,
    `<meta property="og:image:type" content="image/png">`, `<meta property="og:image:width" content="${W}">`, `<meta property="og:image:height" content="${H}">`,
    `<meta property="og:image:alt" content="${esc(d.alt)}">`, `<meta name="twitter:card" content="summary_large_image">`,
    `<meta name="twitter:title" content="${esc(d.title)}">`, `<meta name="twitter:description" content="${esc(d.description)}">`,
    `<meta name="twitter:image" content="${imgUrl}">`, `<meta name="twitter:image:alt" content="${esc(d.alt)}">`, "",
  ].join("\n");
}
function previewHtml(d, card, before, rows, teams) {
  const fig = (label, f) => `<h2>${label}</h2>\n<p><img src="${esc(f.name)}" width="${f.w}" height="${f.h}" alt="${esc(label + ": " + d.alt)}"></p>\n<p>${esc(f.name)}: ${f.w} by ${f.h} px, ${f.size} bytes, SHA-256 <code>${f.sha}</code></p>`;
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Card preview: ${esc(d.site_name)}</title>
</head>
<body>
<main>
<h1>Card preview: ${esc(d.site_name)}</h1>
<p>For the owner's approval before the live card is replaced. Not linked from the site; remove it after the decision.</p>
${before ? fig("Before (the card served today)", before) : "<h2>Before</h2>\n<p>No before image was given.</p>"}
${fig("After (built by build_card.js)", card)}
<h2>How Microsoft Teams shows it</h2>
<p>Teams keeps the full height and shows the centre ${TEAMS.r - TEAMS.l} px of the width (x ${TEAMS.l} to ${TEAMS.r}), measured on 2026-11-05 from 1 Teams preview; other Teams clients may crop differently.</p>
${teams.before ? fig("Before, as Teams crops it", teams.before) : ""}
${fig("After, as Teams crops it", teams.after)}
<h2>Measurements of the after image</h2>
<table>
<tr><th scope="col">Measure</th><th scope="col">Value</th></tr>
${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("\n")}
</table>
</main>
</body>
</html>
`;
}

// ---------------------------------------------------------------- main
function parseArgs(argv) {
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], val = () => { if (i + 1 >= argv.length) { usage(a + " needs a value"); } return argv[++i]; };
    if (a === "--data") { o.data = val(); } else if (a === "--out") { o.out = val(); } else if (a === "--before") { o.before = val(); }
    else if (a === "--palettes") { o.palettes = val(); } else if (a === "--icons-only") { o.iconsOnly = true; } else { usage("unknown argument " + a); }
  }
  if (!o.data || !o.out) { usage("--data and --out are required"); }
  if (o.iconsOnly && o.before) { usage("--before belongs to a card build, not to --icons-only"); }
  return o;
}

// The Teams crop (from 1.10.0): the centre of the width at the image's full height, round(h * 784 / 630) px wide,
// copied pixel for pixel; it scales nothing, so it is the Teams view (x 208 to 992 of the 1200 by 630 card) at the
// image's own size. From 1.11.3 (owner, 2026-11-07): the card, always 1200 by 630, is cropped with before = null
// and any other size is a failure; a --before image, cropped with before = its path, may have any size in the
// exact proportion 1200:630, tested in integers as w and h greater than 0 and w * 630 === h * 1200 (600 by 315
// and 2400 by 1260 pass, 1200 by 628 and 0 by 0 fail). main tests that rule on the IHDR width and height before
// decodePng, so a wrong --before image (an undecodable or a huge PNG included) stops the build, through Fail and
// with the same message, before the image is decoded, any browser is launched or any file is written; teamsCrop
// keeps the same checks for any other caller.
function teamsCrop(img, before = null) {
  if (before === null && (img.w !== W || img.h !== H)) { throw new Fail(`the card is ${img.w} by ${img.h} px; the Teams crop takes only a ${W} by ${H} px image`); }
  if (before !== null && (img.w <= 0 || img.h <= 0 || img.w * H !== img.h * W)) { throw new Fail(`--before ${before} is ${img.w} by ${img.h} px, not in the proportion ${W}:${H} (w and h greater than 0 and w * ${H} must equal h * ${W})`); }
  const cw = Math.round(img.h * (TEAMS.r - TEAMS.l) / H), x0 = Math.floor((img.w - cw) / 2), px = new Uint8Array(cw * img.h * 3);
  for (let y = 0; y < img.h; y++) { px.set(img.px.subarray((y * img.w + x0) * 3, (y * img.w + x0 + cw) * 3), y * cw * 3); }
  return { w: cw, h: img.h, px };
}

// The browser: Playwright's full Chromium, resolved once; every launch passes this path, so the binary that renders
// is the one the report records.
function resolveChromium() {
  let chromium;
  try { ({ chromium } = require("playwright")); } catch (e) { throw new Fail("build_card.js needs the playwright package: " + e.message); }
  const exe = chromium.executablePath(), build = path.basename(exe);
  if (build.includes("headless-shell")) {
    throw new Fail(`the resolved browser build is ${build}, a headless shell, not full Chromium; install the full build with "npx playwright install chromium" and rerun`);
  }
  return { chromium, exe, build };
}

// The icon inputs, read and checked before any browser is launched or any file is written: the logo (an SVG, or
// from 1.12.2 a PNG), the touch icon's background, and from 1.12.2 the favicon (an SVG, or a PNG, whose frames are
// made here). Each input file is added to the report's inputs, the favicon after the logo and the palettes.
function readIcons(d, o, inputs) {
  const ic = { logoSvg: null, touchPng: null, favSvg: null, frames: null, notes: [] };
  let touchBg = d.touch_bg || null;
  if (d.logoPath) {
    let logoPng = null;
    if (/\.png$/i.test(d.logoPath)) { logoPng = readPngInput(d.logoPath, "logo"); inputs.push([d.logoPath, logoPng.buf]); }
    else { ic.logoSvg = checkSvg(d.logoPath, "logo"); inputs.push([d.logoPath, ic.logoSvg]); }
    if (!touchBg) {
      const pal = o.palettes || path.join(__dirname, "..", "palettes.css");
      let cssBuf; try { cssBuf = fs.readFileSync(pal); } catch (e) { throw new Fail(`cannot read ${pal} for the touch icon's --bg (or set touch_bg): ${e.message}`); }
      inputs.push([pal, cssBuf]); // card-report.txt promises the SHA-256 of every input (the header, lines 18 to 19)
      const css = cssBuf.toString("utf8");
      const m = css.match(new RegExp(`\\.site-${d.site}\\s*\\{([^}]*)\\}`));
      const bg = m && m[1].match(/--bg:\s*(#[0-9a-fA-F]{6})/);
      if (!bg) { throw new Fail(`${pal} has no light --bg for site-${d.site}; set touch_bg in the data file`); }
      touchBg = bg[1];
    }
    ic.touchBg = touchBg;
    if (logoPng) {
      ic.touchPng = pngTouch(logoPng.img, touchBg, d.logoPath);
      ic.notes.push(`${d.site}-touch.png: 180 by 180 px, the ${logoPng.img.w} by ${logoPng.img.h} px PNG logo unscaled at the centre, on ${touchBg}`);
    }
  }
  if (d.faviconPath) {
    if (/\.png$/i.test(d.faviconPath)) {
      const fav = readPngInput(d.faviconPath, "favicon"); inputs.push([d.faviconPath, fav.buf]);
      ic.frames = pngFaviconFrames(fav.img, d.faviconPath);
      ic.notes.push(`${d.site}-favicon.ico: frames ${ICO_SIZES.join(", ")} px, each downscaled (Lanczos) from the PNG favicon's visible pixels on a transparent square; the 32 and 16 px frames also as ${d.site}-favicon-32.png and ${d.site}-favicon-16.png`);
    } else {
      ic.favSvg = checkSvg(d.faviconPath, "favicon"); inputs.push([d.faviconPath, ic.favSvg]);
      ic.notes.push(`${d.site}-favicon.ico: frames ${ICO_SIZES.join(", ")} px, each rendered from the SVG favicon at its own size in Chromium`);
    }
  }
  if (ic.notes.length) { ic.notes.push("The .ico frames, PNG favicons and PNG-logo touch icon encoded as Pillow 12.1.1 encodes them"); }
  return ic;
}
// The report's Icons block: the notes, then the Node.js and zlib versions, which every icon PNG goes through.
function iconsBlock(notes) {
  return ["Icons:", ...notes.map((x) => "  " + x), `  Node.js ${process.versions.node}, zlib ${process.versions.zlib} (every icon PNG is compressed with this zlib)`, ""];
}
// The favicon frames from an SVG, rendered in a page of the given browser; every request refused.
async function renderFavicon(browser, svg, onRequest) {
  const page = await browser.newPage({ viewport: { width: 200, height: 200 }, deviceScaleFactor: 1 });
  await page.route("**/*", (r) => { onRequest(); r.abort(); });
  const frames = [];
  for (const n of ICO_SIZES) { frames.push(await svgFrame(page, svg, n)); }
  await page.close();
  return frames;
}
// Each favicon frame exactly its size with at least 1 visible pixel; failures as messages.
function checkFrames(frames) {
  const bad = [];
  for (const f of frames) {
    if (f.px.length !== f.n * f.n * 4) { bad.push(`the ${f.n} px favicon frame is not ${f.n} by ${f.n} px`); continue; }
    let vis = 0; for (let i = 3; i < f.px.length; i += 4) { if (f.px[i]) { vis++; } }
    if (!vis) { bad.push(`the ${f.n} px favicon frame is empty`); }
  }
  return bad;
}
// The icon files, written by write(name, buf) in a fixed order: the favicon.ico and, from a PNG favicon, its 32 and
// 16 px frames as PNG files. (The touch icon is written by the caller.)
function writeFavicon(d, frames, write) {
  const { ico, pngs } = icoFile(frames);
  write(`${d.site}-favicon.ico`, ico);
  if (!d.faviconPath || !/\.png$/i.test(d.faviconPath)) { return; }
  write(`${d.site}-favicon-32.png`, pngs[ICO_SIZES.indexOf(32)]);
  write(`${d.site}-favicon-16.png`, pngs[ICO_SIZES.indexOf(16)]);
}
// The touch icon of an SVG logo: the logo at 144 px centred on the background, opaque, as from 1.9.0.
async function svgTouch(browser, svg, bg, onRequest) {
  const page = await browser.newPage({ viewport: { width: 180, height: 180 }, deviceScaleFactor: 1 });
  await page.route("**/*", (r) => { onRequest(); r.abort(); });
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:180px;height:180px;overflow:hidden;background:${bg}}img{position:absolute;left:18px;top:18px;width:144px;height:144px;object-fit:contain}</style></head><body><img src="data:image/svg+xml;base64,${svg.toString("base64")}" alt=""></body></html>`, { waitUntil: "load" });
  const tp = decodePng(await page.screenshot({ type: "png" }));
  await page.close();
  return rgbPng(tp);
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  if (o.iconsOnly) { return iconsOnly(o); }
  const { chromium, exe, build } = resolveChromium();
  const d = readData(o.data);
  const inputs = [[o.data, fs.readFileSync(o.data)]];
  const artSvg = checkSvg(d.artPath, "illustration"); inputs.push([d.artPath, artSvg]);
  const ic = readIcons(d, o, inputs), { logoSvg } = ic;
  let before = null;
  if (o.before) {

    let b; try { b = fs.readFileSync(o.before); } catch (e) { throw new Fail(`cannot read --before ${o.before}: ${e.message}`); }
    // Before the IHDR width and height are read: the full 8-byte PNG signature, a length that holds an IHDR and
    // the IHDR chunk type at bytes 12 to 15, each failing through Fail with 1 clear message of its own, so a
    // truncated file or one without an IHDR chunk fails with its message, not a read error; from 1.11.4 the IHDR
    // length field (bytes 8 to 11) must equal 13, so a malformed length fails here with 1 message instead of
    // failing later in decodePng or being accepted although the PNG specification requires 13.
    if (b.length < 8 || !b.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) { throw new Fail(`--before ${o.before} is not a PNG (it does not start with the 8-byte PNG signature)`); }
    if (b.length < 24) { throw new Fail(`--before ${o.before} is truncated at ${b.length} bytes, too short to hold a PNG IHDR`); }
    if (b.toString("ascii", 12, 16) !== "IHDR") { throw new Fail(`--before ${o.before} is not a valid PNG (its first chunk is not IHDR)`); }
    const ihdrLen = b.readUInt32BE(8);
    if (ihdrLen !== 13) { throw new Fail(`--before ${o.before} is not a valid PNG (its IHDR chunk declares a length of ${ihdrLen} bytes, not 13)`); }
    const img = { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
    // The proportion rule on the IHDR width and height, before decodePng, so a wrong --before image (an
    // undecodable or a huge PNG included) fails with this one message, before the image is decoded, a browser
    // is launched or a file is written. teamsCrop keeps the same checks for any other caller.
    if (img.w <= 0 || img.h <= 0 || img.w * H !== img.h * W) { throw new Fail(`--before ${o.before} is ${img.w} by ${img.h} px, not in the proportion ${W}:${H} (w and h greater than 0 and w * ${H} must equal h * ${W})`); }
    before = { buf: b, teams: teamsCrop(decodePng(b), o.before), name: `${d.site}-card-before.png`, w: img.w, h: img.h, size: b.length, sha: sha(b) };
  }
  const cmaps = [];
  const fonts = FONT_FILES.map(([f, wt]) => {
    const p = path.join(__dirname, "card-fonts", f); let b;
    try { b = fs.readFileSync(p); } catch (e) { throw new Fail(`cannot read the bundled font ${p}: ${e.message}`); }
    inputs.push([p, b]); cmaps.push(cmapCodepoints(b)); return [`data:font/otf;base64,${b.toString("base64")}`, wt];
  });
  const texts = [d.name, d.tld, d.line1, d.line2, d.sub, d.formula ? d.formula.replace(/[{}[\]]/g, "") : ""].join("");
  const missing = [...new Set([...texts].filter((ch) => ch.trim() && !cmaps.every((set) => set.has(ch.codePointAt(0)))))];
  const artUri = `data:image/svg+xml;base64,${artSvg.toString("base64")}`;
  const html = cardPage(d, fonts, artUri);
  const centre = d.layout === "centre", safeArea = centre ? CSAFE : SAFE, colW = centre ? CSAFE.w : COL;

  const browser = await chromium.launch({ executablePath: exe }); // exactly the resolved binary the report records
  let refused = 0;
  const failures = [];
  const render = async (variant) => { // a fresh page per render: variant "card", "safe" or "bg"
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    await page.route("**/*", (r) => { refused++; r.abort(); });
    await page.setContent(html, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    const fit = await page.evaluate(FIT, { COL, nowrap: !!d.sub_nowrap, centre, C: { w: CSAFE.w, h: CSAFE.h, artMax: C_ART_MAX, artMin: C_ART_MIN, gap: C_GAP } });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const m = await page.evaluate(MEASURE);
    if (variant === "safe") {
      await page.evaluate(({ s, t }) => {
        const add = (css) => { const g = document.createElement("div"); g.style.cssText = css + ";position:absolute;pointer-events:none"; document.querySelector(".card").appendChild(g); };
        add(`left:${s.l}px;top:${s.t}px;width:${s.w - 2}px;height:${s.h - 2}px;border:2px dotted #ff3b3b`);
        add(`left:${t.l}px;top:0;width:${t.r - t.l - 2}px;height:${630 - 2}px;border:2px dashed #22d3ee`);
      }, { s: safeArea, t: TEAMS });
    }
    if (variant === "bg") { await page.addStyleTag({ content: ".text,.formula{visibility:hidden}" }); }
    const png = await page.screenshot({ type: "png" });
    await page.close();
    return { fit, m, img: decodePng(png) };
  };
  const card = await render("card");
  const again = await render("card");
  const safe = await render("safe");
  const bgr = await render("bg");
  // From 1.12.2: the favicon frames of an SVG favicon, in the same browser, before any check is reported.
  let frames = ic.frames;
  if (ic.favSvg) { frames = await renderFavicon(browser, ic.favSvg, () => { refused++; }); }
  const version = browser.version();
  await browser.close();
  if (frames) { failures.push(...checkFrames(frames)); }

  const { fit, m } = card;
  // Checks
  if (card.img.w !== W || card.img.h !== H) { failures.push(`the render is ${card.img.w} by ${card.img.h} px, not ${W} by ${H}`); }
  if (missing.length) { failures.push(`characters not in the bundled Inter: ${missing.join(" ")}`); }
  if (!fit.brand.fits) { failures.push(`the wordmark does not fit the ${colW} px column at its floor of 60 px`); }
  if (!fit.lines.fits) { failures.push(`a statement line does not fit the ${colW} px column at its floor of 20 px`); }
  if (fit.formula && !fit.formula.fits) { failures.push(`the formula row does not fit ${centre ? colW : 960} px at its floor of 20 px`); }
  if (fit.sub && !fit.sub.fits) { failures.push(`the 1-line subline does not fit the ${colW} px column at its floor of 18 px`); }
  if (centre && !fit.art.fits) { failures.push(`the text leaves ${fit.art.size} px for the illustration (needs ${C_ART_MIN}): shorten the text or use layout = "side"`); }
  const cl = m.clear, needLR = safeArea.l, needTB = safeArea.t;
  if (cl.left < needLR - 0.5 || cl.right < W - safeArea.l - safeArea.w - 0.5 || cl.top < needTB - 0.5 || cl.bottom < H - safeArea.t - safeArea.h - 0.5) {
    failures.push(`content leaves the safe area: clearance left ${cl.left.toFixed(1)}, right ${cl.right.toFixed(1)}, top ${cl.top.toFixed(1)}, bottom ${cl.bottom.toFixed(1)} px (needs ${needLR}, ${needLR}, ${needTB}, ${needTB})`);
  }
  if (!centre && m.gap < GAP - 0.05) { failures.push(`the gap between the text and the illustration is ${m.gap.toFixed(1)} px (needs ${GAP})`); }
  if (centre && m.vgap < C_GAP - 0.05) { failures.push(`the gap between the illustration and the text is ${m.vgap.toFixed(1)} px (needs ${C_GAP})`); }
  if (sha(Buffer.from(card.img.px)) !== sha(Buffer.from(again.img.px))) { failures.push("2 renders of the same inputs differ"); }
  const b = m.boxes, white = [255, 255, 255];
  const con = { line1: worstContrast(bgr.img, b.l1, white, 1), line2: worstContrast(bgr.img, b.l2, white, 1), subline: worstContrast(bgr.img, b.sub, white, 0.88),
    wordmark: worstContrast(bgr.img, b.brand, hexRgb(d.word_colour), 1), wordmark_tld: worstContrast(bgr.img, b.brand, hexRgb(GOLD), 1) };
  if (b.formula) { Object.assign(con, { formula_white: worstContrast(bgr.img, b.formula, white, 1), formula_gold: worstContrast(bgr.img, b.formula, hexRgb(GOLD), 1), formula_blue: worstContrast(bgr.img, b.formula, hexRgb(BLUE), 1) }); }
  // From 1.11.5 a gradient fill is measured at its worst stop: the lowest ratio of its stops against the brightest
  // background pixel, and 1:1 when that pixel's luminance lies within the stops' own range.
  const worstStops = (box, stops) => {
    const r = stops.map((c) => worstContrast(bgr.img, box, hexRgb(c), 1)).reduce((x, y) => (y.ratio < x.ratio ? y : x));
    const ls = stops.map((c) => lum(hexRgb(c))), lb = lum(hexRgb(r.bg));
    return lb >= Math.min(...ls) && lb <= Math.max(...ls) ? { ratio: 1, bg: r.bg } : r;
  };
  if (d.word_style === "metal") { con.wordmark = worstStops(b.brand, PLAT_STOPS); con.wordmark_tld = worstStops(b.brand, GOLD_STOPS); }
  for (const [k, v] of Object.entries(con)) { const need = /^(line|sub)/.test(k) ? 4.5 : 3; if (v.ratio < need) { failures.push(`contrast of ${k} is ${v.ratio}:1 on ${v.bg} (needs ${need}:1)`); } }

  const f1 = (x) => x.toFixed(1), f2 = (x) => x.toFixed(2);
  const rows = [
    ["Layout", centre ? "centre" : "side"],
    ["Text column", `${colW} px`], ["Illustration rendered size", `${f1(m.artW)} x ${f1(m.artH)} px`],
    ["Wordmark size and width", `${f2(m.brandPx)} px, ${f2(m.brandW)} px wide`], ["Statement line size (both lines)", `${f2(m.linePx)} px`],
    ["Subline", `${f2(m.subPx)} px, ${m.subLines} line${m.subLines === 1 ? "" : "s"}`],
  ];
  if (m.formulaPx) { rows.push(["Formula row size", `${f2(m.formulaPx)} px, width ${f2(b.formula.r - b.formula.l)} px`]); }
  rows.push([`Clearance: left, right, top, bottom (needs ${needLR}, ${needLR}, ${needTB}, ${needTB})`, `${f1(cl.left)}, ${f1(cl.right)}, ${f1(cl.top)}, ${f1(cl.bottom)} px`],
    centre ? [`Gap between the illustration and the text (needs ${C_GAP})`, `${f1(m.vgap)} px`] : ["Gap between text and illustration (needs 28)", `${f1(m.gap)} px`]);
  // The Teams crop (from 1.10.0): reported for both layouts, a finding for review and never a failure on its own.
  const names = { brand: "wordmark", rule: "rule", l1: "statement line 1", l2: "statement line 2", sub: "subline", art: "illustration", formula: "formula row" };
  const cut = Object.entries(m.boxes).filter(([, x]) => x.l < TEAMS.l - 0.5 || x.r > TEAMS.r + 0.5).map(([k]) => names[k]);
  rows.push([`Teams crop (x ${TEAMS.l} to ${TEAMS.r}): clearance left, right`, `${f1(m.span.l - TEAMS.l)}, ${f1(TEAMS.r - m.span.r)} px`],
    ["Teams crop: cut at the edges", cut.length ? cut.join(", ") : "nothing"]);
  for (const [k, v] of Object.entries(con)) { rows.push([`Contrast, ${k.replace(/_/g, " ")} (needs ${/^(line|sub)/.test(k) ? "4.5" : "3"}:1)`, `${v.ratio}:1 on ${v.bg}`]); }

  const report = [`build_card.js report for ${d.site_name} (baseline ${VERSION}, layout ${d.layout})`, "", `Chromium ${version} (${build}); ${refused} request(s) refused`, ""];
  report.push("Measurements:", ...rows.map(([k, v]) => `  ${k}: ${v}`), "");
  report.push("Inputs (SHA-256):", ...inputs.map(([p, buf]) => `  ${sha(buf)}  ${path.relative(process.cwd(), p) || p}`), "");
  // The background check (from 1.9.2): the 256-colour card against the full-colour render, outside the safe area.
  const q = quantize(card.img, safeArea);
  rows.push([`Background check: largest change outside the safe area (at most ${MARGIN_MAX})`, `${q.marginDev} levels`]);
  report.splice(report.indexOf("Inputs (SHA-256):") - 1, 0, `  ${rows[rows.length - 1][0]}: ${rows[rows.length - 1][1]}`);
  // From 1.12.2: what the icons are made from, after the measurements and before the inputs.
  if (ic.notes.length) { report.splice(report.indexOf("Inputs (SHA-256):"), 0, ...iconsBlock(ic.notes)); }
  if (q.marginDev > MARGIN_MAX) { failures.push(`the background check: a pixel outside the safe area differs from the full-colour render by ${q.marginDev} levels (at most ${MARGIN_MAX})`); }
  if (failures.length) {
    report.push("RESULT: fail", ...failures.map((x) => "  FAIL " + x));
    fs.mkdirSync(o.out, { recursive: true });
    fs.writeFileSync(path.join(o.out, "card-report.txt"), report.join("\n") + "\n");
    console.log(report.join("\n"));
    process.exit(1);
  }

  // Outputs
  fs.mkdirSync(o.out, { recursive: true });
  const written = [];
  const write = (name, buf) => { fs.writeFileSync(path.join(o.out, name), buf); written.push([name, buf]); return buf; };
  const cardPng = write(`${d.site}-card.png`, q);
  write(`${d.site}-card-safe.png`, quantize(safe.img, safeArea));
  // The Teams crops (from 1.10.0): teamsCrop, above main; the --before image's crop was made as it was read.
  const teamsAfter = teamsCrop(decodePng(q)), teamsAfterPng = write(`${d.site}-card-teams.png`, rgbPng(teamsAfter));
  const teams = { after: { name: `${d.site}-card-teams.png`, w: teamsAfter.w, h: teamsAfter.h, size: teamsAfterPng.length, sha: sha(teamsAfterPng) }, before: null };
  if (logoSvg) {
    const browser2 = await chromium.launch({ executablePath: exe }); // exactly the resolved binary the report records
    const touch = await svgTouch(browser2, logoSvg, ic.touchBg, () => { refused++; });
    await browser2.close();
    write(`${d.site}-touch.png`, touch);
  } else if (ic.touchPng) { write(`${d.site}-touch.png`, ic.touchPng); } // from 1.12.2, a PNG logo
  if (frames) { writeFavicon(d, frames, write); } // from 1.12.2
  const imgUrl = `https://${d.domain}/images/${d.site}-card.png`;
  write("card-tags.html", Buffer.from(tagsHtml(d, imgUrl)));
  if (before) {
    write(before.name, before.buf);
    const tb = before.teams, tbPng = write(`${d.site}-card-before-teams.png`, rgbPng(tb));
    teams.before = { name: `${d.site}-card-before-teams.png`, w: tb.w, h: tb.h, size: tbPng.length, sha: sha(tbPng) };
  }
  const after = { name: `${d.site}-card.png`, w: W, h: H, size: cardPng.length, sha: sha(cardPng) };
  write("cardpreview.html", Buffer.from(previewHtml(d, after, before, rows, teams)));
  report.push("RESULT: pass", "", "Files written (SHA-256):", ...written.map(([n, buf]) => `  ${sha(buf)}  ${n}`));
  fs.writeFileSync(path.join(o.out, "card-report.txt"), report.join("\n") + "\n");
  console.log(report.join("\n"));
  process.exit(0);
}

// --icons-only (from 1.12.2): the icons and the report, no card. Placed after main, so that in the source the
// --before crop still comes before the first browser launch (release check t_v1113).
async function iconsOnly(o) {
  const d = readData(o.data, true);
  const inputs = [[o.data, fs.readFileSync(o.data)]];
  const ic = readIcons(d, o, inputs);
  let refused = 0, head = "No browser launched (no SVG input)", touch = ic.touchPng, frames = ic.frames;
  if (ic.logoSvg || ic.favSvg) {
    const { chromium, exe, build } = resolveChromium();
    const browser = await chromium.launch({ executablePath: exe }); // exactly the resolved binary the report records
    if (ic.logoSvg) {
      touch = await svgTouch(browser, ic.logoSvg, ic.touchBg, () => { refused++; });
      ic.notes.unshift(`${d.site}-touch.png: 180 by 180 px, the SVG logo at 144 px centred on ${ic.touchBg}`);
    }
    if (ic.favSvg) { frames = await renderFavicon(browser, ic.favSvg, () => { refused++; }); }
    head = `Chromium ${browser.version()} (${build}); ${refused} request(s) refused`;
    await browser.close();
  }
  const report = [`build_card.js report for ${d.site} (baseline ${VERSION}, icons only)`, "", head, ""];
  if (ic.notes.length) { report.push(...iconsBlock(ic.notes)); }
  report.push("Inputs (SHA-256):", ...inputs.map(([p, buf]) => `  ${sha(buf)}  ${path.relative(process.cwd(), p) || p}`), "");
  const failures = frames ? checkFrames(frames) : [];
  fs.mkdirSync(o.out, { recursive: true });
  if (failures.length) {
    report.push("RESULT: fail", ...failures.map((x) => "  FAIL " + x));
    fs.writeFileSync(path.join(o.out, "card-report.txt"), report.join("\n") + "\n");
    console.log(report.join("\n"));
    process.exit(1);
  }
  const written = [];
  const write = (name, buf) => { fs.writeFileSync(path.join(o.out, name), buf); written.push([name, buf]); return buf; };
  if (touch) { write(`${d.site}-touch.png`, touch); }
  if (frames) { writeFavicon(d, frames, write); }
  report.push("RESULT: pass", "", "Files written (SHA-256):", ...written.map(([n, buf]) => `  ${sha(buf)}  ${n}`));
  fs.writeFileSync(path.join(o.out, "card-report.txt"), report.join("\n") + "\n");
  console.log(report.join("\n"));
  process.exit(0);
}

if (require.main === module) {
  main().catch((e) => {
    if (e instanceof Fail) { console.log("RESULT: fail\n  FAIL " + e.message); process.exit(1); }
    console.error("ERROR: " + (e && e.stack ? e.stack : e)); console.log("RESULT: fail (the builder could not run)"); process.exit(1);
  });
} else {
  module.exports = { decodePng, parseToml, VERSION, teamsCrop }; // for the template owner's release checks
}
