/* select.js: the install selector. Marks the chosen assistant and hides the other sections.
   Markup: <ul class="picker" data-picker><li><a href="#claude" data-family-link="claude">Claude</a></li>...</ul>
           <button class="btn picker-reset" type="button" data-picker-reset hidden>Show all assistants</button>
           <p class="vh" role="status" data-picker-status></p>
           <section id="claude" data-family-section="claude">...</section>
   Without this script every section stays visible and the links are plain in-page anchors.
   Accepts ?ai=<family> and #<family> on load, and follows later hash changes. */
(function () {
  "use strict";
  var picker = document.querySelector("[data-picker]");
  if (!picker) { return; }
  var links = picker.querySelectorAll("a[data-family-link]");
  var sections = document.querySelectorAll("[data-family-section]");
  var reset = document.querySelector("[data-picker-reset]");
  var status = document.querySelector("[data-picker-status]");
  var families = [];
  Array.prototype.forEach.call(links, function (a) { families.push(a.getAttribute("data-family-link")); });

  function choose(family) {
    var known = families.indexOf(family) >= 0;
    Array.prototype.forEach.call(sections, function (s) {
      s.hidden = known && s.getAttribute("data-family-section") !== family;
    });
    var chosenLabel = "";
    Array.prototype.forEach.call(links, function (a) {
      var mine = known && a.getAttribute("data-family-link") === family;
      if (mine) { a.setAttribute("aria-current", "true"); chosenLabel = a.textContent; } else { a.removeAttribute("aria-current"); }
    });
    if (reset) { reset.hidden = !known; }
    if (status) { status.textContent = known ? "Showing the steps for " + chosenLabel + ". The other assistants are hidden." : "Showing every assistant."; }
    if (known) {
      var section = document.getElementById(family);
      if (section) { section.setAttribute("tabindex", "-1"); section.focus({ preventScroll: true }); section.scrollIntoView({ block: "start" }); }
    }
  }

  Array.prototype.forEach.call(links, function (a) {
    a.addEventListener("click", function (event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) { return; }
      event.preventDefault();
      choose(a.getAttribute("data-family-link"));
      if (history.replaceState) { history.replaceState(null, "", location.pathname + location.search); }
    });
  });
  if (reset) {
    reset.addEventListener("click", function () { choose(null); picker.setAttribute("tabindex", "-1"); picker.focus(); });
  }
  window.addEventListener("hashchange", function () {
    var h = location.hash.replace("#", "");
    if (families.indexOf(h) >= 0) { choose(h); }
  });

  var q = /[?&]ai=([a-z-]+)/.exec(location.search);
  var initial = q ? q[1] : location.hash.replace("#", "");
  if (families.indexOf(initial) >= 0) { choose(initial); }
})();
