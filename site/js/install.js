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

  function familyFromHash() {
    var name = location.hash.slice(1);
    return FAMILIES.indexOf(name) === -1 ? null : name;
  }

  function render(family, announce) {
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
    if (status && announce) {
      status.textContent = family
        ? 'Showing the ' + NAMES[family] + ' setup. The other sections stay below.'
        : 'Showing every setup section.';
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

  if (reset) {
    reset.addEventListener('click', function () {
      render(null, true);
      history.replaceState(null, '', location.pathname + location.search);
      if (picker) { picker.focus(); }
    });
  }
  window.addEventListener('hashchange', function () { apply(true); });

  apply(false);
  var initial = familyFromHash();
  if (initial) {
    var target = document.getElementById(initial);
    if (target) { target.scrollIntoView(); }
  }
})();
