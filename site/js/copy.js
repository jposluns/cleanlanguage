document.querySelectorAll('[data-copy-target]').forEach(function (button) {
  button.hidden = false;
  button.addEventListener('click', function () {
    var source = document.getElementById(button.getAttribute('data-copy-target'));
    if (!source) return;
    var status = document.getElementById('copy-status');
    var original = button.textContent;
    function report(buttonText, message) {
      button.textContent = buttonText;
      if (status) { status.textContent = message; }
      setTimeout(function () {
        button.textContent = original;
        if (status) { status.textContent = ''; }
      }, 4000);
    }
    function fallback() {
      var range = document.createRange();
      range.selectNodeContents(source);
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      report('Press Ctrl+C to copy', 'Copy failed. The text is selected; copy it with Ctrl+C or long press.');
    }
    if (!navigator.clipboard) { fallback(); return; }
    navigator.clipboard.writeText(source.textContent).then(function () {
      report('Copied', 'Copied to clipboard');
    }, fallback);
  });
});
