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
   From 1.7.0, per group, opt-in: data-filter-empty="disable" on the group's element marks a chip that would show no
   rows with the current query and other choices aria-disabled="true" (it stays focusable; activating it is refused
   and the status says why); data-filter-count="live" also sets each chip's .n to its would-show count. A page with
   no opted-in group runs exactly as in 1.6.1.
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
    groups.push({ name: name, chips: Array.prototype.slice.call(el.querySelectorAll("[data-filter]")), value: "",
      empty: el.getAttribute("data-filter-empty") === "disable", live: el.getAttribute("data-filter-count") === "live" });
  });
  var counting = groups.some(function (g) { return g.empty || g.live; });
  var NOTE = "filter-empty-note";
  /* Opted-in pages only: each row's lowercased text and group tokens, prepared once (live counts change chip text,
     never row text, but the cache keeps every update to 1 pass over prepared data). */
  var prep = counting ? rows.map(function (li) {
    var tok = {};
    groups.forEach(function (g) { tok[g.name] = words(low(li, "data-" + g.name)).filter(function (v, i, a) { return a.indexOf(v) === i; }); });
    return { li: li, hay: (li.getAttribute("data-search") || li.textContent).toLowerCase(), tok: tok };
  }) : null;
  if (counting && !document.getElementById(NOTE)) {
    var note = document.createElement("p");
    note.id = NOTE;
    note.hidden = true;
    note.textContent = "Would show no documents with the current choices";
    document.body.appendChild(note);
  }
  function labelOf(c) {
    var text = c.textContent;
    Array.prototype.forEach.call(c.querySelectorAll(".vh, .n"), function (v) { text = text.replace(v.textContent, ""); });
    return text.replace(/\s+/g, " ").trim();
  }
  function describe(c, on) {
    var ids = (c.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    var has = ids.indexOf(NOTE) >= 0;
    if (on === has) { return; }
    ids = on ? ids.concat(NOTE) : ids.filter(function (x) { return x !== NOTE; });
    if (ids.length) { c.setAttribute("aria-describedby", ids.join(" ")); } else { c.removeAttribute("aria-describedby"); }
  }
  /* 1 pass over the rows: a row that fails nothing counts toward its values in every group and every All; a row that
     fails only 1 group's choice counts toward that group (its values and its All); a row that fails the query, or 2
     or more groups, counts nowhere. Then each opted-in chip takes its count and state; the DOM changes only where a
     state or a count changes. Returns 1 flag per row, in the order of rows: true where the row shows. */
  function count(terms, active, idle) {
    var tally = {};
    groups.forEach(function (g) { tally[g.name] = { all: 0, v: {} }; });
    var shown = prep.map(function (r) {
      if (!terms.every(function (t) { return r.hay.indexOf(t) >= 0; })) { return false; }
      var failed = active.filter(function (g) { return r.tok[g.name].indexOf(g.value) < 0; });
      if (failed.length < 2) {
        (failed.length ? failed : groups).forEach(function (g) {
          var t = tally[g.name];
          t.all += 1;
          r.tok[g.name].forEach(function (v) { t.v[v] = (t.v[v] || 0) + 1; });
        });
      }
      return !failed.length && !(results && idle);
    });
    groups.forEach(function (g) {
      if (!g.empty && !g.live) { return; }
      g.chips.forEach(function (c) {
        var v = low(c, "data-filter");
        var n = v ? tally[g.name].v[v] || 0 : tally[g.name].all;
        if (g.live) {
          var el = c.querySelector(".n");
          if (el && el.textContent !== String(n)) { el.textContent = String(n); }
        }
        var off = g.empty && v !== "" && v !== g.value && n === 0;
        if (off !== (c.getAttribute("aria-disabled") === "true")) {
          if (off) { c.setAttribute("aria-disabled", "true"); } else { c.removeAttribute("aria-disabled"); }
        }
        if (g.empty) { describe(c, off); }
      });
    });
    return shown;
  }

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
    var pass = counting ? count(terms, active, idle) : null;
    rows.forEach(function (li, i) {
      var ok;
      if (pass) {
        ok = pass[i];
      } else {
        var hay = (li.getAttribute("data-search") || li.textContent).toLowerCase();
        ok = !(results && idle) &&
          terms.every(function (t) { return hay.indexOf(t) >= 0; }) &&
          active.every(function (g) { return words(low(li, "data-" + g.name)).indexOf(g.value) >= 0; });
      }
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
        if (c.getAttribute("aria-disabled") === "true") {
          if (status) { status.textContent = labelOf(c) + " would show no documents with the current choices."; }
          return;
        }
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
