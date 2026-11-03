/* search.js: filters the document list already on the page.
   Markup: <form class="search" role="search" data-search><label for="q">...</label><input id="q" type="search">
           <p class="status" role="status" data-search-status></p></form>
           <ul class="plan" data-search-scope><li data-search="title type area purpose frameworks">...</li></ul>
   Without this script the whole list and the browse chips stay visible; the input does nothing.
   The live site would load its search index (search-index.json) the same way; the mockup filters the rows it shows. */
(function () {
  "use strict";
  var form = document.querySelector("[data-search]");
  var scope = document.querySelector("[data-search-scope]");
  if (!form || !scope) { return; }
  var input = form.querySelector("input[type=search]");
  var status = form.querySelector("[data-search-status]");
  var rows = scope.querySelectorAll("li");
  var total = rows.length;
  form.addEventListener("submit", function (e) { e.preventDefault(); });
  function run() {
    var terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    var shown = 0;
    Array.prototype.forEach.call(rows, function (li) {
      var hay = (li.getAttribute("data-search") || li.textContent).toLowerCase();
      var ok = terms.every(function (t) { return hay.indexOf(t) >= 0; });
      li.hidden = !ok;
      if (ok) { shown += 1; }
    });
    if (status) {
      status.textContent = terms.length ? shown + " of " + total + " documents match." : "";
    }
  }
  input.addEventListener("input", run);
  run();
})();
