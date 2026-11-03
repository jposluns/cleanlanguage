/* scheme.js: the light and dark switch in the top bar (from 1.6.0).
   Load it on every page in <head>, before the stylesheets, with no defer or async, so that a stored choice
   applies before the first paint:  <script data-cfasync="false" src=".../scheme.js"></script>
   (data-cfasync="false", before src, keeps Cloudflare Rocket Loader from deferring it.)
   Markup, the last item of header.mast, after nav.nav:
     <button class="scheme" type="button" data-scheme-toggle aria-pressed="false" hidden>
       <svg class="moon" ...></svg><svg class="sun" ...></svg><span class="vh">Dark mode</span></button>
   The page follows the device setting (prefers-color-scheme) until the reader presses the switch; a press sets
   data-scheme="light" or "dark" on <html> and stores it in localStorage under "scheme". aria-pressed is "true"
   while dark mode is showing. Blocked storage is caught: the choice then lasts for the page only. Without this
   script the button keeps its hidden attribute, so no reader sees a switch that does nothing. */
(function () {
  "use strict";
  var KEY = "scheme";
  var root = document.documentElement;

  function read() {
    try {
      var v = window.localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) { return null; }
  }
  function write(v) {
    try { window.localStorage.setItem(KEY, v); } catch (e) { /* storage blocked: the choice lasts for this page */ }
  }

  var stored = read();
  if (stored) { root.setAttribute("data-scheme", stored); }
  var media = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function isDark() {
    var forced = root.getAttribute("data-scheme");
    if (forced === "dark" || forced === "light") { return forced === "dark"; }
    return !!(media && media.matches);
  }

  function wire() {
    var buttons = document.querySelectorAll("[data-scheme-toggle]");
    if (!buttons.length) { return; }
    function sync() {
      var pressed = isDark() ? "true" : "false";
      Array.prototype.forEach.call(buttons, function (b) { b.setAttribute("aria-pressed", pressed); });
    }
    Array.prototype.forEach.call(buttons, function (b) {
      b.addEventListener("click", function () {
        var next = isDark() ? "light" : "dark";
        root.setAttribute("data-scheme", next);
        write(next);
        sync();
      });
      b.hidden = false;
    });
    if (media) {
      if (media.addEventListener) { media.addEventListener("change", sync); } else if (media.addListener) { media.addListener(sync); }
    }
    sync();
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", wire); } else { wire(); }
})();
