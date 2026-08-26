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

  function scrollToFamily(family) {
    if (!family) { return; }
    var target = document.getElementById(family);
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
      if (location.hash) {
        history.replaceState(null, '', location.pathname + location.search);
      }
    });
  });

  if (reset) {
    reset.addEventListener('click', function () {
      render(null, true);
      history.replaceState(null, '', location.pathname + location.search);
      if (picker) { picker.focus(); }
    });
  }

  // A hash-driven change (a deep link from another page, Back or Forward, or a
  // typed URL) does scroll to the named family; an in-page tap above does not.
  window.addEventListener('hashchange', function () {
    var before = current;
    var family = familyFromHash();
    apply(true);
    if (family && family !== before) { scrollToFamily(family); }
  });

  apply(false);
  scrollToFamily(familyFromHash());
})();
