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
    if (target) { target.scrollIntoView(); }
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

  if (reset) {
    reset.addEventListener('click', function () {
      render(null, true);
      history.replaceState(null, '', location.pathname + location.search);
      if (picker) { picker.focus(); }
    });
  }

  window.addEventListener('hashchange', function () {
    var family = familyFromHash();
    apply(true);
    // The browser scrolled to the target against the pre-collapse page; after
    // collapsing the sections above it, the target has moved, so restore it.
    scrollToFamily(family);
  });

  apply(false);
  scrollToFamily(familyFromHash());
})();
