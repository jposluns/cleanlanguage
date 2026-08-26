document.querySelectorAll('[data-copy-target]').forEach(function (button) {
  button.hidden = false;
  var original = button.textContent;
  var resetTimer = null;
  var isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || '');
  var copyKey = isMac ? 'Cmd+C' : 'Ctrl+C';
  button.addEventListener('click', function () {
    var source = document.getElementById(button.getAttribute('data-copy-target'));
    if (!source) return;
    var status = document.getElementById('copy-status');
    function report(buttonText, message) {
      button.textContent = buttonText;
      if (status) { status.textContent = message; }
      if (resetTimer) { clearTimeout(resetTimer); }
      resetTimer = setTimeout(function () {
        button.textContent = original;
        if (status) { status.textContent = ''; }
        resetTimer = null;
      }, 4000);
    }
    function fallback() {
      var range = document.createRange();
      range.selectNodeContents(source);
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      report('Press ' + copyKey + ' to copy', 'Copy failed. The text is selected; copy it with ' + copyKey + ', or long press on a touch screen.');
    }
    if (!navigator.clipboard) { fallback(); return; }
    navigator.clipboard.writeText(source.textContent).then(function () {
      report('Copied', 'Copied to clipboard');
    }, fallback);
  });
});
