/* rail.js: marks the rail link of the section the reader is on.
   Markup: <nav class="rail" aria-label="On this page"> with links to in-page sections (href="#id").
   The section whose top has passed the reading line (a quarter of the viewport down) is current; at the end
   of the page the last section in view is current; a rail click or a page opened at #id marks that section.
   The current link carries aria-current="location"; every other link carries none. Without this script no
   link is marked, which is accurate. No storage, no network, no motion. */
(function () {
  "use strict";
  var rail = document.querySelector("nav.rail");
  if (!rail || !window.requestAnimationFrame) { return; }
  var items = [];
  Array.prototype.forEach.call(rail.querySelectorAll('a[href^="#"]'), function (link) {
    var id = decodeURIComponent(link.getAttribute("href").slice(1));
    var target = id ? document.getElementById(id) : null;
    link.removeAttribute("aria-current");
    if (target) { items.push({ link: link, target: target }); }
  });
  if (!items.length) { return; }

  var current = null;
  var pinnedUntil = 0;

  function mark(item) {
    if (item === current) { return; }
    items.forEach(function (it) {
      if (it === item) { it.link.setAttribute("aria-current", "location"); }
      else { it.link.removeAttribute("aria-current"); }
    });
    current = item;
  }

  function pick() {
    var line = window.innerHeight * 0.25;
    var chosen = null;
    items.forEach(function (it) {
      if (it.target.getBoundingClientRect().top <= line) { chosen = it; }
    });
    var doc = document.documentElement;
    if (window.innerHeight + window.scrollY >= doc.scrollHeight - 2) {
      items.forEach(function (it) {
        if (it.target.getBoundingClientRect().top < window.innerHeight) { chosen = it; }
      });
    }
    if (!chosen && items[0].target.getBoundingClientRect().top < window.innerHeight) { chosen = items[0]; }
    return chosen;
  }

  var queued = false;
  function update() {
    queued = false;
    if (Date.now() < pinnedUntil) { return; }
    mark(pick());
  }
  function queue() {
    if (!queued) { queued = true; window.requestAnimationFrame(update); }
  }

  function fromHash() {
    var id = decodeURIComponent(window.location.hash.slice(1));
    for (var i = 0; i < items.length; i += 1) {
      if (items[i].target.id === id) { mark(items[i]); pinnedUntil = Date.now() + 400; return true; }
    }
    return false;
  }

  items.forEach(function (it) {
    it.link.addEventListener("click", function () { mark(it); pinnedUntil = Date.now() + 400; });
  });
  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", queue);
  window.addEventListener("hashchange", fromHash);
  if (!fromHash()) { update(); }
}());
