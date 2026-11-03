/* copy.js: copy-to-clipboard for prompt and command blocks.
   Markup: <pre id="X" class="hascopy"><button class="copy" type="button" data-copy="X" hidden>Copy</button>...</pre>
   Without this script the button stays hidden and the text stays selectable. */
(function () {
  "use strict";
  if (!navigator.clipboard || !navigator.clipboard.writeText) { return; }
  var status = document.getElementById("copy-status");
  var buttons = document.querySelectorAll("button[data-copy]");
  Array.prototype.forEach.call(buttons, function (button) {
    var target = document.getElementById(button.getAttribute("data-copy"));
    if (!target) { return; }
    button.hidden = false;
    button.addEventListener("click", function () {
      var text = target.textContent;
      if (button.parentNode === target) { text = text.replace(button.textContent, ""); }
      navigator.clipboard.writeText(text.trim()).then(function () {
        var label = button.textContent;
        button.textContent = "Copied";
        if (status) { status.textContent = "Copied to the clipboard."; }
        setTimeout(function () { button.textContent = label; if (status) { status.textContent = ""; } }, 3000);
      }, function () {
        if (status) { status.textContent = "Copy failed. Select the text and copy it yourself."; }
      });
    });
  });
})();
