/*
  The phone menu
  ==============

  Without this file, a small screen shows every nav link, wrapped onto as
  many rows as they need. Nothing is hidden, so nothing needs a button.

  With this file, the header gets the class site-header--menu. Only then does
  the CSS show the Menu button and fold the links away behind it. That order
  matters: if this script failed to load, a CSS rule that hid the links on
  its own would leave a visitor with no navigation and a button that does
  nothing. The script switches the menu on, so the menu can only exist when
  the script that runs it does.

  The state lives in ONE place, the button's aria-expanded attribute. This
  script flips it; the CSS reads it to hide or show the nav; a screen reader
  reads it to say "collapsed" or "expanded". None of them keeps a copy.

  Above the 64em breakpoint the CSS ignores all of this and shows the full
  row, whatever aria-expanded says.
*/

(function () {
  "use strict";

  var header = document.querySelector(".site-header");
  var toggle = header && header.querySelector(".menu-toggle");
  var nav = toggle && document.getElementById(toggle.getAttribute("aria-controls"));
  if (!nav) {
    return;
  }

  header.classList.add("site-header--menu");

  function isOpen() {
    return toggle.getAttribute("aria-expanded") === "true";
  }

  function setOpen(open) {
    toggle.setAttribute("aria-expanded", String(open));
  }

  toggle.addEventListener("click", function () {
    setOpen(!isOpen());
  });

  // Escape closes the menu and puts focus back on the button, the way a
  // dialog behaves. Only while focus is in the header: the lightbox uses
  // Escape too, and that press is not meant for the menu.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isOpen() && header.contains(document.activeElement)) {
      setOpen(false);
      toggle.focus();
    }
  });
})();
