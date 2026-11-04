/* search.js: filters the document list already on the page; optional facets and results-only mode (from 1.5.0).
   Markup: <form class="search" role="search" data-search><label for="q">...</label><input id="q" type="search">
           <p class="status" role="status" data-search-status></p></form>
           <ul class="plan" data-search-scope><li data-search="title type area purpose frameworks">...</li></ul>
   Default mode, as in 1.4.1: an empty query shows every row; a query shows the rows holding every term.
   data-search-mode="results" on the scope: no row shows until the reader types or picks a facet, the status shows
   data-search-prompt (or "Type to search the documents."), and rows whose title (data-title, or the first link's
   text) holds every term come first, in page order; data-search-rank="title" turns the ranking on in default mode.
   Facets: <ul class="chips" data-filter-group="domain"> of links or buttons with data-filter="privacy" (data-filter=""
   is All); rows carry data-domain="privacy risk". The state is read from ?q= and ?<group>= and written back with
   history.replaceState. SPECIFICATION.md section 7.29 has the full contract.
   Without this script every row stays visible, the chips are plain links and the input does nothing. */
(function () {
  "use strict";
  var scope = document.querySelector("[data-search-scope]");
  if (!scope) { return; }
  var form = document.querySelector("[data-search]");
  var groupEls = document.querySelectorAll("[data-filter-group]");
  if (!form && !groupEls.length) { return; }
  var input = form ? form.querySelector("input[type=search]") : null;
  var status = form ? form.querySelector("[data-search-status]") : document.querySelector("[data-search-status]");
  var rows = Array.prototype.slice.call(scope.querySelectorAll("li"));
  var total = rows.length;
  var results = scope.getAttribute("data-search-mode") === "results";
  var rank = results || scope.getAttribute("data-search-rank") === "title";
  var prompt = scope.getAttribute("data-search-prompt") || "Type to search the documents.";
  var urlOK = !!(window.URLSearchParams && window.history && window.history.replaceState);
  var groups = [];

  function low(el, name) { return (el.getAttribute(name) || "").toLowerCase(); }
  function words(text) { return text.toLowerCase().split(/\s+/).filter(Boolean); }

  Array.prototype.forEach.call(groupEls, function (el) {
    var name = low(el, "data-filter-group");
    if (!/^[a-z][a-z0-9-]*$/.test(name) || name === "q") { return; }
    groups.push({ name: name, chips: Array.prototype.slice.call(el.querySelectorAll("[data-filter]")), value: "" });
  });

  function titleOf(li) {
    if (li.hasAttribute("data-title")) { return li.getAttribute("data-title").toLowerCase(); }
    var a = li.querySelector("a");
    if (!a) { return ""; }
    var text = a.textContent;
    Array.prototype.forEach.call(a.querySelectorAll(".vh"), function (v) { text = text.replace(v.textContent, ""); });
    return text.toLowerCase();
  }

  function order(list) {
    var now = scope.querySelectorAll("li");
    var same = list.every(function (li, i) { return now[i] === li; });
    if (same) { return; }
    list.forEach(function (li) { li.parentNode.appendChild(li); });
  }

  function run() {
    var terms = input ? words(input.value) : [];
    var active = groups.filter(function (g) { return g.value; });
    var idle = !terms.length && !active.length;
    var shown = 0;
    var first = [];
    var rest = [];
    var out = [];
    rows.forEach(function (li) {
      var hay = (li.getAttribute("data-search") || li.textContent).toLowerCase();
      var ok = !(results && idle) &&
        terms.every(function (t) { return hay.indexOf(t) >= 0; }) &&
        active.every(function (g) { return words(low(li, "data-" + g.name)).indexOf(g.value) >= 0; });
      li.hidden = !ok;
      if (ok) {
        shown += 1;
        var title = rank && terms.length ? titleOf(li) : "";
        (title && terms.every(function (t) { return title.indexOf(t) >= 0; }) ? first : rest).push(li);
      } else {
        out.push(li);
      }
    });
    if (rank) { order(terms.length ? first.concat(rest, out) : rows); }
    if (!status) { return; }
    if (results && idle) {
      status.textContent = prompt;
    } else if (groups.length) {
      status.textContent = "Showing " + shown + " of " + total + " documents.";
    } else {
      status.textContent = terms.length ? shown + " of " + total + " documents match." : "";
    }
  }

  function paint() {
    groups.forEach(function (g) {
      g.chips.forEach(function (c) { c.setAttribute("aria-pressed", low(c, "data-filter") === g.value ? "true" : "false"); });
    });
  }

  function write() {
    if (!urlOK) { return; }
    var p = new URLSearchParams(window.location.search);
    if (input) {
      if (input.value.trim()) { p.set("q", input.value); } else { p.delete("q"); }
    }
    groups.forEach(function (g) {
      if (g.value) { p.set(g.name, g.value); } else { p.delete(g.name); }
    });
    var s = p.toString();
    window.history.replaceState(window.history.state, "", window.location.pathname + (s ? "?" + s : "") + window.location.hash);
  }

  if (urlOK) {
    var params = new URLSearchParams(window.location.search);
    if (input && params.has("q")) { input.value = params.get("q"); }
    groups.forEach(function (g) {
      var v = (params.get(g.name) || "").toLowerCase();
      if (v && g.chips.some(function (c) { return low(c, "data-filter") === v; })) { g.value = v; }
    });
  }

  if (form) { form.addEventListener("submit", function (e) { e.preventDefault(); }); }
  if (input) { input.addEventListener("input", function () { run(); write(); }); }
  groups.forEach(function (g) {
    g.chips.forEach(function (c) {
      if (c.tagName === "A") {
        c.setAttribute("role", "button");
        c.addEventListener("keydown", function (e) {
          if (e.key === " " || e.key === "Spacebar") { e.preventDefault(); c.click(); }
        });
      }
      c.addEventListener("click", function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) { return; }
        e.preventDefault();
        var v = low(c, "data-filter");
        g.value = v && v !== g.value ? v : "";
        paint();
        run();
        write();
      });
    });
  });
  paint();
  run();
})();
