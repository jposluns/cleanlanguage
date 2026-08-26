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

  function scrollToGet() {
    // A family selection lands the reader at Get Clean Language, filtered, so they
    // get the file first and then work down to their assistant's steps, rather
    // than jumping straight to that section.
    var target = document.getElementById('get');
    if (!target) { return; }
    try {
      target.scrollIntoView({ block: 'start', behavior: 'auto' });
    } catch (e) {
      target.scrollIntoView();
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

  // A hash-driven change (a legacy deep link, Back or Forward, or a typed URL)
  // selects that family and lands at Get Clean Language.
  window.addEventListener('hashchange', function () {
    var family = familyFromHash();
    apply(true);
    // Any #family hash triggers a native scroll to that section; correct it to Get
    // whether or not the filter changed. A non-family hash is left to scroll natively.
    if (family) { scrollToGet(); }
  });

  var queryFamily = familyFromQuery();
  if (queryFamily) {
    render(queryFamily, false);
  } else {
    apply(false);
  }
  if (queryFamily || familyFromHash()) {
    // Land at Get Clean Language on the next frame: this also corrects the native
    // scroll a legacy #family deep link triggers.
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(scrollToGet);
    } else {
      scrollToGet();
    }
  }
})();
