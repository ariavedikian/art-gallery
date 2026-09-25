/*
  Artwork lightbox
  ================

  Click an artwork in any grid and it opens large, in place, with previous
  and next controls. Escape or a click outside closes it.

  Why this is JavaScript and not Python
  -------------------------------------
  Everything else on this site is decided on the server: the browser asks for
  a URL, Flask queries SQLite, and a finished page comes back. That round trip
  is the right shape when the answer depends on data the browser does not
  have.

  Opening a viewer is not that. Nothing new is needed from the database — the
  title, artist, medium and price are already on the page — and a server
  cannot react to a keypress without being asked. So this runs where the
  interaction happens: in the browser.

  It also degrades gracefully. Every card is a real link to a real page. If
  this file fails to load, or JavaScript is switched off, clicking a card
  still works. The lightbox is an enhancement, never the only way through.
*/

(function () {
  "use strict";

  // --- Find the pieces we need ---------------------------------------------

  var dialog = document.getElementById("lightbox");
  var grids = document.querySelectorAll(".artwork-grid");
  var cards = Array.prototype.slice.call(document.querySelectorAll(".artwork"));

  // Bail out quietly if this page has no grid, or the browser is too old for
  // <dialog>. Doing nothing leaves the plain links working.
  if (!dialog || !cards.length || typeof dialog.showModal !== "function") {
    return;
  }

  var view = {
    image: document.getElementById("lightbox-image"),
    title: document.getElementById("lightbox-title"),
    meta: document.getElementById("lightbox-meta"),
    description: document.getElementById("lightbox-description"),
    price: document.getElementById("lightbox-price"),
    link: document.getElementById("lightbox-link"),
    count: document.getElementById("lightbox-count"),
    controls: document.getElementById("lightbox-controls")
  };

  // --- Read the data the server already put in the page ---------------------

  // Each card carries its details in data-* attributes, which JavaScript reads
  // through .dataset: data-artist becomes card.dataset.artist. No extra
  // request is needed, because the server rendered this data with the page.
  //
  // The price line is copied straight out of the card instead. The rule for
  // what it says (Sold, an edition count, not for sale) lives in one Jinja
  // macro; rewriting that rule here in JavaScript would mean two copies of it
  // that could disagree.
  //
  // This runs each time the viewer opens rather than once at load, and skips
  // hidden cards: Stage 10 lets the filter hide works, and paging through
  // pieces the visitor has filtered out would be a small lie.
  function collectWorks() {
    return cards.filter(function (card) {
      return !card.hidden;
    }).map(function (card) {
      return {
        card: card,
        title: card.dataset.title,
        artist: card.dataset.artist,
        year: card.dataset.year,
        medium: card.dataset.medium,
        description: card.dataset.description,
        image: card.dataset.image,
        srcset: card.dataset.srcset,
        href: card.dataset.href,
        price: card.querySelector(".price"),
        // Copied from the card's own <img>, for the same reason as the price:
        // the alt text is decided once, on the server, not rebuilt here.
        alt: card.querySelector("img").alt
      };
    });
  }

  var works = [];

  // The whole state of this feature: which work is showing. One number.
  var index = 0;

  // --- Rendering ------------------------------------------------------------

  function show(nextIndex) {
    // Wrap around in both directions: after the last comes the first, and
    // going back from the first lands on the last. The modulo of a negative
    // number is negative in JavaScript, so add the length before taking it.
    index = (nextIndex + works.length) % works.length;

    var work = works[index];

    // srcset BEFORE src, so the browser chooses from the list rather than
    // starting to fetch the full-size original first. Assigned every time,
    // even when empty: a placeholder has no srcset, and skipping the
    // assignment would leave the previous work's list in place.
    view.image.srcset = work.srcset;
    view.image.src = work.image;
    view.image.alt = work.alt;
    view.title.textContent = work.title;
    view.meta.textContent = work.artist + ", " + work.year + " · " + work.medium;
    view.description.textContent = work.description;
    view.link.href = work.href;
    view.count.textContent = (index + 1) + " of " + works.length;

    // The price line is ELEMENTS (spans with classes), so textContent would
    // lose them. It used to be copied as an HTML string through innerHTML,
    // which turns text back into markup -- safe only as long as nothing in
    // that string ever came from a person. Copying the nodes themselves
    // never parses anything: what was text on the card stays text here.
    // cloneNode(true) copies the card's line, leaving the card's own intact.
    view.price.replaceChildren(...work.price.cloneNode(true).childNodes);
  }

  function open(card) {
    works = collectWorks();

    // Paging only makes sense with something to page to.
    view.controls.hidden = works.length < 2;

    var start = works.findIndex(function (work) {
      return work.card === card;
    });

    show(start === -1 ? 0 : start);
    // showModal, not show: it puts the dialog above everything else, dims the
    // page behind it, keeps Tab inside it, and closes on Escape. All of that
    // is behaviour the browser gives us for free.
    dialog.showModal();
  }

  // --- Events ---------------------------------------------------------------

  // One listener per grid, not one per card. The click lands on a child and
  // bubbles up to the list, where closest() finds which card it came from.
  // This is event delegation: fewer listeners, and it would keep working if
  // cards were ever added to the page later.
  grids.forEach(function (grid) {
    grid.addEventListener("click", function (event) {
      // Let ctrl-click, middle-click and shift-click do their normal jobs:
      // people expect those to open the link in a tab or window.
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
        return;
      }

      var card = event.target.closest(".artwork");
      if (!card) {
        return;
      }

      // The card is a link to the artwork page. preventDefault stops the
      // browser following it so the viewer can open instead.
      event.preventDefault();
      open(card);
    });
  });

  document.getElementById("lightbox-next").addEventListener("click", function () {
    show(index + 1);
  });

  document.getElementById("lightbox-prev").addEventListener("click", function () {
    show(index - 1);
  });

  document.getElementById("lightbox-close").addEventListener("click", function () {
    dialog.close();
  });

  dialog.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight") {
      show(index + 1);
    } else if (event.key === "ArrowLeft") {
      show(index - 1);
    } else if (event.key === "Escape") {
      // A modal <dialog> is supposed to close on Escape by itself, and in a
      // standards-compliant browser this line changes nothing: close() on an
      // already-closing dialog does nothing. It is here because the browser
      // this was tested in never fired that built-in close request, and
      // Escape is too important to leave to trust alone.
      dialog.close();
    }
  });

  // Click outside to close. The dialog has no padding, so its own box is
  // exactly the backdrop area around the content: if the click landed on the
  // dialog itself rather than on something inside it, it was outside.
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      dialog.close();
    }
  });
})();
