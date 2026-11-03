/* matrix.js: column presets for a matrix table (from 1.5.0).
   Markup: presets anywhere on the page, as buttons or links, each with data-preset (the column keys it shows,
           space-separated) and data-preset-id (its name in the address): <a href="..." data-preset="iso27001 csf soc2"
           data-preset-id="security">Security</a>; the All preset has data-preset="" and shows every column.
           <p class="matrix-status" role="status" aria-live="polite" data-matrix-status></p>
           <table class="matrix sticky sticky-col" data-matrix> with data-col="<key>" on every th and td of a preset
           column; the row-header column carries no data-col and always shows. 1 matrix per page, 1 header row.
   Choosing a preset hides the other columns with the hidden attribute and writes the status ("View: Security.
   Showing 3 of 8 columns."). The chosen preset carries aria-pressed="true" when it is a button (the others "false"),
   and aria-current="true" when it is a link (the others none): a link keeps its link role and leads to a page that
   resolves. A modified click (new tab, new window) is left to the browser. ?view=<preset-id> chooses a preset on
   load (an unknown id is ignored); a choice is written back with history.replaceState, and All removes the parameter.
   Without this script every column shows and each preset is a plain link. No colspan handling: by design the
   matrix has a single header row. */
(function () {
  "use strict";
  var table = document.querySelector("table[data-matrix]");
  if (!table) { return; }
  var presets = Array.prototype.slice.call(document.querySelectorAll("[data-preset]"));
  if (!presets.length) { return; }
  var status = document.querySelector("[data-matrix-status]");
  var heads = Array.prototype.slice.call(table.querySelectorAll("thead th[data-col]"));
  var cells = Array.prototype.slice.call(table.querySelectorAll("th[data-col], td[data-col]"));
  var urlOK = !!(window.URLSearchParams && window.history && window.history.replaceState);

  function keys(p) { return (p.getAttribute("data-preset") || "").toLowerCase().split(/\s+/).filter(Boolean); }
  function label(p) {
    var text = p.textContent;
    Array.prototype.forEach.call(p.querySelectorAll(".vh, .n"), function (v) { text = text.replace(v.textContent, ""); });
    return text.replace(/\s+/g, " ").trim();
  }

  function choose(p, write) {
    var k = keys(p);
    cells.forEach(function (c) {
      c.hidden = k.length > 0 && k.indexOf((c.getAttribute("data-col") || "").toLowerCase()) < 0;
    });
    presets.forEach(function (q) {
      var mine = q === p;
      if (q.tagName === "A") {
        if (mine) { q.setAttribute("aria-current", "true"); } else { q.removeAttribute("aria-current"); }
      } else {
        q.setAttribute("aria-pressed", mine ? "true" : "false");
      }
    });
    var shown = heads.filter(function (h) { return !h.hidden; }).length;
    if (status) { status.textContent = "View: " + label(p) + ". Showing " + shown + " of " + heads.length + " columns."; }
    if (write && urlOK) {
      var s = new URLSearchParams(window.location.search);
      var id = p.getAttribute("data-preset-id");
      if (k.length && id) { s.set("view", id); } else { s.delete("view"); }
      var qs = s.toString();
      window.history.replaceState(window.history.state, "", window.location.pathname + (qs ? "?" + qs : "") + window.location.hash);
    }
  }

  presets.forEach(function (p) {
    p.addEventListener("click", function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) { return; }
      e.preventDefault();
      choose(p, true);
    });
  });

  var start = null;
  if (urlOK) {
    var view = new URLSearchParams(window.location.search).get("view");
    if (view) { start = presets.filter(function (p) { return p.getAttribute("data-preset-id") === view; })[0] || null; }
  }
  if (!start) { start = presets.filter(function (p) { return !keys(p).length; })[0] || null; }
  if (start) { choose(start, false); }
})();
