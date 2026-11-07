#!/usr/bin/env node
/* build_card.js: the link-preview card builder (baseline 1.9.0 and later; the dithering limit and the background
   check from 1.9.2; the centred layout, the Teams crop and the version label from 1.10.0).

   From 1 data file and 1 approved illustration per site it renders, in headless Chromium with the bundled Inter
   fonts (card-fonts/, SIL OFL 1.1, never served):
     <site>-card.png        the 1200 by 630 link-preview image, reduced to 256 colours (median cut, Floyd-Steinberg)
     <site>-card-safe.png   the same render with the layout's safe area outlined in red dots and the Microsoft Teams
                            crop in cyan dashes; for review, never served
     <site>-card-teams.png  the part of the card Teams shows (x 208 to 992, 784 by 630); for review, never served
     <site>-touch.png       the 180 by 180 Apple touch icon (the logo at 144 px, centred on the site's light --bg,
                            opaque), when the data file names a logo
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
   The Teams crop is measured for both layouts and reported (the clearance of the content inside x 208 to 992, and
   what lies outside it); with the centre layout the safe area keeps the content inside it, and with the side layout
   it is a finding for the owner's review, never a failure.

   Usage:
     node build_card.js --data <site-card.toml> --out <folder> [--before <png>] [--palettes <palettes.css>]
   --before   the card the site serves today, shown as "before" in cardpreview.html
   --palettes the baseline's palettes.css, for the touch icon's light --bg (default: the package's own,
              ../palettes.css); a data file may set touch_bg instead
   Needs Node.js 18 or later and the playwright package with its Chromium. Nothing is fetched: every request
   the page makes is refused, and the fonts, illustration and logo are read from disk.
   Exit status: 0 when every check passes and every file is written; 1 when any check fails or an input cannot
   be read; 2 for a usage error. Repeatable on 1 machine: the same inputs and the same Chromium build give the
   same SHA-256; another Chromium build may draw text edges differently, so the report records its version. */
"use strict";
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const crypto = require("crypto");

// The package version this builder belongs to; the report and the tags name it. The release checks fail when it
// differs from the package's version.
const VERSION = "1.11.1";
const W = 1200, H = 630, SAFE = { l: 120, t: 75, w: 960, h: 480 };
const ART = 430, ART_BOX = 340, GAP = 28, COL = SAFE.w - ART_BOX - GAP;
// The centred layout (from 1.10.0) and the Microsoft Teams crop it keeps clear of.
const TEAMS = { l: 208, r: 992 }, CSAFE = { l: 248, t: 50, w: 704, h: 530 };
const C_ART_MAX = 250, C_ART_MIN = 140, C_GAP = 18;
const GOLD = "#fbbf24", BLUE = "#5eb0ef";
const FONT_FILES = [["Inter-Regular.otf", 400], ["Inter-Bold.otf", 700], ["Inter-ExtraBold.otf", 800]];

class Fail extends Error {}
function usage(msg) {
  if (msg) { console.error("usage error: " + msg); }
  console.error("usage: node build_card.js --data <site-card.toml> --out <folder> [--before <png>] [--palettes <palettes.css>]");
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
  logo: "optional: the site's full-colour logo SVG, for the touch icon", word_colour: "the wordmark name's colour, #rrggbb",
  background: "the card background, CSS gradients and colours only", touch_bg: "optional: the touch icon's background, #rrggbb",
  site_name: "optional: the site name in the tags (default name + tld)", domain: "optional (default: name + tld, lowercase)",
  title: "optional og:title", description: "optional og:description", alt: "optional og:image:alt",
};
function readData(file) {
  let text;
  try { text = fs.readFileSync(file, "utf8"); } catch (e) { throw new Fail(`cannot read ${file}: ${e.message}`); }
  const d = parseToml(text, file);
  for (const k of Object.keys(d)) { if (!(k in FIELDS)) { throw new Fail(`${file}: unknown field ${k}`); } }
  for (const k of ["site", "name", "line1", "line2", "sub", "art", "word_colour", "background"]) {
    if (typeof d[k] !== "string" || !d[k].trim()) { throw new Fail(`${file}: ${k} is required (${FIELDS[k]})`); }
  }
  for (const k of ["tld", "formula", "layout", "logo", "touch_bg", "site_name", "domain", "title", "description", "alt"]) {
    if (k in d && typeof d[k] !== "string") { throw new Fail(`${file}: ${k} must be a string`); }
  }
  if ("sub_nowrap" in d && typeof d.sub_nowrap !== "boolean") { throw new Fail(`${file}: sub_nowrap must be true or false`); }
  d.layout = d.layout || "side";
  if (d.layout !== "side" && d.layout !== "centre") { throw new Fail(`${file}: layout must be "side" or "centre"`); }
  if (!/^[a-z0-9-]+$/.test(d.site)) { throw new Fail(`${file}: site: ${FIELDS.site}`); }
  if (!/^#[0-9a-fA-F]{6}$/.test(d.word_colour)) { throw new Fail(`${file}: word_colour must be #rrggbb`); }
  if (d.touch_bg && !/^#[0-9a-fA-F]{6}$/.test(d.touch_bg)) { throw new Fail(`${file}: touch_bg must be #rrggbb`); }
  if (!/^[a-zA-Z0-9#(),.%\s-]+$/.test(d.background) || /url\s*\(|expression|var\s*\(/i.test(d.background)) {
    throw new Fail(`${file}: background may hold only CSS gradients, colours, lengths and percentages`);
  }
  const dir = path.dirname(path.resolve(file));
  d.tld = d.tld || ".ai";
  d.site_name = d.site_name || d.name + d.tld;
  d.domain = d.domain || (d.name + d.tld).toLowerCase();
  if (!/^[a-z0-9.-]+$/.test(d.domain)) { throw new Fail(`${file}: domain must be a host name`); }
  d.title = d.title || `${d.site_name} - ${d.line1.replace(/\.$/, "")}`;
  d.description = d.description || d.sub;
  d.alt = d.alt || `${d.site_name}: ${d.line1} ${d.line2}`;
  d.artPath = path.resolve(dir, d.art);
  d.logoPath = d.logo ? path.resolve(dir, d.logo) : null;
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
function decodePng(buf) {
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
  const out = new Uint8Array(w * h * 3), prev = new Uint8Array(stride), cur = new Uint8Array(stride);
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
      if (ctype === 3) { const k = cur[x] * 3; out[(y * w + x) * 3] = plte[k]; out[(y * w + x) * 3 + 1] = plte[k + 1]; out[(y * w + x) * 3 + 2] = plte[k + 2]; continue; }
      out[(y * w + x) * 3] = cur[x * bpp]; out[(y * w + x) * 3 + 1] = cur[x * bpp + 1]; out[(y * w + x) * 3 + 2] = cur[x * bpp + 2];
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

// ---------------------------------------------------------------- 256 colours: median cut, Floyd-Steinberg
// From 1.9.2 the dithering is limited: a pixel never takes a palette colour more than DITHER_LIMIT levels (in any
// channel) from its own colour, and the error passed on is capped at the same amount. Without the limit (1.9.0 and
// 1.9.1), where the palette had no colour close to a smooth area on one side, the error carried forward until it
// reached a distant colour: auditthis.ai's card had 13 stray grey and blue pixels at the centre of a gradient.
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
</style></head><body><div class="card"><div class="safe">
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
    else if (a === "--palettes") { o.palettes = val(); } else { usage("unknown argument " + a); }
  }
  if (!o.data || !o.out) { usage("--data and --out are required"); }
  return o;
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  let chromium;
  try { ({ chromium } = require("playwright")); } catch (e) { throw new Fail("build_card.js needs the playwright package: " + e.message); }
  const d = readData(o.data);
  const inputs = [[o.data, fs.readFileSync(o.data)]];
  const artSvg = checkSvg(d.artPath, "illustration"); inputs.push([d.artPath, artSvg]);
  let logoSvg = null, touchBg = d.touch_bg || null;
  if (d.logoPath) {
    logoSvg = checkSvg(d.logoPath, "logo"); inputs.push([d.logoPath, logoSvg]);
    if (!touchBg) {
      const pal = o.palettes || path.join(__dirname, "..", "palettes.css");
      let css; try { css = fs.readFileSync(pal, "utf8"); } catch (e) { throw new Fail(`cannot read ${pal} for the touch icon's --bg (or set touch_bg): ${e.message}`); }
      const m = css.match(new RegExp(`\\.site-${d.site}\\s*\\{([^}]*)\\}`));
      const bg = m && m[1].match(/--bg:\s*(#[0-9a-fA-F]{6})/);
      if (!bg) { throw new Fail(`${pal} has no light --bg for site-${d.site}; set touch_bg in the data file`); }
      touchBg = bg[1];
    }
  }
  let before = null;
  if (o.before) {
    let b; try { b = fs.readFileSync(o.before); } catch (e) { throw new Fail(`cannot read --before ${o.before}: ${e.message}`); }
    const img = b.readUInt32BE(0) === 0x89504e47 ? { w: b.readUInt32BE(16), h: b.readUInt32BE(20) } : null;
    if (!img) { throw new Fail(`--before ${o.before} is not a PNG`); }
    before = { buf: b, img: decodePng(b), name: `${d.site}-card-before.png`, w: img.w, h: img.h, size: b.length, sha: sha(b) };
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

  const browser = await chromium.launch();
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
  const version = browser.version();
  await browser.close();

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

  const report = [`build_card.js report for ${d.site_name} (baseline ${VERSION}, layout ${d.layout})`, "", `Chromium ${version}; ${refused} request(s) refused`, ""];
  report.push("Measurements:", ...rows.map(([k, v]) => `  ${k}: ${v}`), "");
  report.push("Inputs (SHA-256):", ...inputs.map(([p, buf]) => `  ${sha(buf)}  ${path.relative(process.cwd(), p) || p}`), "");
  // The background check (from 1.9.2): the 256-colour card against the full-colour render, outside the safe area.
  const q = quantize(card.img, safeArea);
  rows.push([`Background check: largest change outside the safe area (at most ${MARGIN_MAX})`, `${q.marginDev} levels`]);
  report.splice(report.indexOf("Inputs (SHA-256):") - 1, 0, `  ${rows[rows.length - 1][0]}: ${rows[rows.length - 1][1]}`);
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
  // The Teams crops (from 1.10.0): the centre of the width, at the image's full height, scaled to 1200 by 630 first.
  const teamsCrop = (img) => {
    const cw = Math.round(img.h * (TEAMS.r - TEAMS.l) / H), x0 = Math.floor((img.w - cw) / 2), px = new Uint8Array(cw * img.h * 3);
    for (let y = 0; y < img.h; y++) { px.set(img.px.subarray((y * img.w + x0) * 3, (y * img.w + x0 + cw) * 3), y * cw * 3); }
    return { w: cw, h: img.h, px };
  };
  const teamsAfter = teamsCrop(decodePng(q)), teamsAfterPng = write(`${d.site}-card-teams.png`, rgbPng(teamsAfter));
  const teams = { after: { name: `${d.site}-card-teams.png`, w: teamsAfter.w, h: teamsAfter.h, size: teamsAfterPng.length, sha: sha(teamsAfterPng) }, before: null };
  if (logoSvg) {
    const browser2 = await chromium.launch();
    const page = await browser2.newPage({ viewport: { width: 180, height: 180 }, deviceScaleFactor: 1 });
    await page.route("**/*", (r) => { refused++; r.abort(); });
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;width:180px;height:180px;overflow:hidden;background:${touchBg}}img{position:absolute;left:18px;top:18px;width:144px;height:144px;object-fit:contain}</style></head><body><img src="data:image/svg+xml;base64,${logoSvg.toString("base64")}" alt=""></body></html>`, { waitUntil: "load" });
    const tp = decodePng(await page.screenshot({ type: "png" }));
    await browser2.close();
    write(`${d.site}-touch.png`, rgbPng(tp));
  }
  const imgUrl = `https://${d.domain}/images/${d.site}-card.png`;
  write("card-tags.html", Buffer.from(tagsHtml(d, imgUrl)));
  if (before) {
    write(before.name, before.buf);
    const tb = teamsCrop(before.img), tbPng = write(`${d.site}-card-before-teams.png`, rgbPng(tb));
    teams.before = { name: `${d.site}-card-before-teams.png`, w: tb.w, h: tb.h, size: tbPng.length, sha: sha(tbPng) };
  }
  const after = { name: `${d.site}-card.png`, w: W, h: H, size: cardPng.length, sha: sha(cardPng) };
  write("cardpreview.html", Buffer.from(previewHtml(d, after, before, rows, teams)));
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
  module.exports = { decodePng, parseToml, VERSION }; // for the template owner's release checks
}
