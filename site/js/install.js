(function () {
  var FAMILIES = ['claude', 'chatgpt', 'gemini', 'copilot', 'other-ai'];
  var NAMES = {
    claude: 'Claude',
    chatgpt: 'ChatGPT',
    gemini: 'Gemini',
    copilot: 'Copilot',
    'other-ai': 'other AI systems'
  };
  var root = document.documentElement;
  var picker = document.getElementById('install-picker');
  var reset = document.getElementById('family-reset');
  var status = document.getElementById('family-status');
  var links = document.querySelectorAll('.platform-actions a[data-family-link]');
  if (!links.length) { return; }
  var current = null;

  function familyFromHash() {
    var name = location.hash.slice(1);
    return FAMILIES.indexOf(name) === -1 ? null : name;
  }

  function familyFromQuery() {
    var query = location.search.charAt(0) === '?' ? location.search.slice(1) : location.search;
    var pairs = query.split('&');
    for (var i = 0; i < pairs.length; i++) {
      var pair = pairs[i].split('=');
      if (pair[0] === 'ai') {
        var name = pair[1] || '';
        try {
          name = decodeURIComponent(name);
        } catch (e) {
          return null;
        }
        return FAMILIES.indexOf(name) === -1 ? null : name;
      }
    }
    return null;
  }

  function render(family, announce) {
    var changed = family !== current;
    if (family) {
      root.setAttribute('data-family', family);
    } else {
      root.removeAttribute('data-family');
    }
    Array.prototype.forEach.call(links, function (link) {
      if (link.getAttribute('data-family-link') === family) {
        link.setAttribute('aria-current', 'true');
      } else {
        link.removeAttribute('aria-current');
      }
    });
    if (reset) { reset.hidden = !family; }
    if (status && announce && changed) {
      status.textContent = family
        ? 'Showing the ' + NAMES[family] + ' setup. Choose Show all AI systems to see the other setups.'
        : 'Showing every setup section.';
    }
    current = family;
  }

  function scrollToTop() {
    // A family selection lands the reader at the top of the page with the picker
    // filtered, not jumped to the section, so they still work down in order.
    try {
      window.scrollTo({ top: 0, behavior: 'auto' });
    } catch (e) {
      window.scrollTo(0, 0);
    }
  }

  function apply(announce) {
    var family = familyFromHash();
    if (family) {
      render(family, announce);
    } else if (!location.hash) {
      render(null, announce);
    }
    // A non-family hash such as #spelling leaves the current view alone.
  }

  // Tapping a picker button filters in place: it hides the other assistants but
  // does NOT jump to the section, so the reader still works down the page in
  // order (pick, get the file, follow the steps, test).
  Array.prototype.forEach.call(links, function (link) {
    link.addEventListener('click', function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey ||
          (typeof e.button === 'number' && e.button !== 0)) {
        return;
      }
      e.preventDefault();
      render(link.getAttribute('data-family-link'), true);
      history.replaceState(null, '', location.pathname);
    });
  });

  if (reset) {
    reset.addEventListener('click', function () {
      render(null, true);
      history.replaceState(null, '', location.pathname);
      if (picker) { picker.focus(); }
    });
  }

  // A hash-driven change (a deep link from another page, Back or Forward, or a
  // typed URL) selects that family and lands at the top, like an in-page tap.
  window.addEventListener('hashchange', function () {
    var before = current;
    var family = familyFromHash();
    apply(true);
    if (family && family !== before) { scrollToTop(); }
  });

  var queryFamily = familyFromQuery();
  if (queryFamily) {
    // A ?ai= deep link: no fragment, so the browser does not scroll. Just filter.
    render(queryFamily, false);
  } else {
    apply(false);
    if (familyFromHash()) {
      // A legacy #family deep link also scrolls to the section; correct it next frame.
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(scrollToTop);
      } else {
        scrollToTop();
      }
    }
  }
})();
