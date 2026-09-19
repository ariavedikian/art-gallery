/*
  Collection filtering, in the browser
  ====================================

  The server sends every artwork to the All works page. This file hides the
  cards that do not match the filters, which makes filtering instant: no
  request, no page reload, no waiting.

  WHY THIS IS REASONABLE HERE, AND WHERE IT STOPS BEING SO

  It works because the whole collection is already on the page. The moment
  that stops being true, this approach breaks, and it breaks quietly:

    * A large collection. Sending 2,000 works to filter down to 12 wastes
      the visitor's bandwidth and the browser's memory. The page gets slower
      for everyone, including people who never touch a filter.
    * Pagination. If the page only holds the first 24 works, this searches
      24 works and confidently reports "no matches" for a piece that exists.
      That is the dangerous failure: a wrong answer, not an error.
    * Sharing. Filters live in memory, not in the URL, so a filtered view
      cannot be linked, bookmarked or reloaded.
    * No JavaScript, no filtering. The controls do nothing at all.

  The fix for every one of those is to filter in SQL and let the server send
  only the matching rows. That is part 2 of this stage.
*/

(function () {
  "use strict";

  var form = document.getElementById("filters");
  var grid = document.querySelector(".artwork-grid");
  if (!form || !grid) {
    return;
  }

  var controls = {
    q: document.getElementById("filter-q"),
    artist: document.getElementById("filter-artist"),
    category: document.getElementById("filter-category"),
    status: document.getElementById("filter-status"),
    price: document.getElementById("filter-price")
  };

  var countLine = document.getElementById("filter-count");
  var emptyLine = document.getElementById("filter-empty");

  // Build the searchable text once, at load, rather than on every keystroke.
  // With six works it makes no difference; the habit is what matters.
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".artwork"));
  var items = cards.map(function (card) {
    return {
      card: card,
      artist: card.dataset.artistSlug,      // data-artist-slug
      category: card.dataset.category,
      status: card.dataset.status,
      price: Number(card.dataset.priceCents),
      text: [
        card.dataset.title,
        card.dataset.artist,
        card.dataset.medium,
        card.dataset.category
      ].join(" ").toLowerCase()
    };
  });

  function matches(item, filters) {
    // Every filter that is set must pass. An unset filter is not a test.
    if (filters.q && item.text.indexOf(filters.q) === -1) {
      return false;
    }
    if (filters.artist && item.artist !== filters.artist) {
      return false;
    }
    if (filters.category && item.category !== filters.category) {
      return false;
    }
    if (filters.status && item.status !== filters.status) {
      return false;
    }
    if (filters.price) {
      // "100000-300000" -> from 100000 to 300000. "300000-" has no ceiling.
      var bounds = filters.price.split("-");
      var low = Number(bounds[0]);
      var high = bounds[1] === "" ? Infinity : Number(bounds[1]);
      if (item.price < low || item.price > high) {
        return false;
      }
    }
    return true;
  }

  function apply() {
    var filters = {
      // Trimmed and lowercased once here, not inside the loop.
      q: controls.q.value.trim().toLowerCase(),
      artist: controls.artist.value,
      category: controls.category.value,
      status: controls.status.value,
      price: controls.price.value
    };

    var shown = 0;
    items.forEach(function (item) {
      var visible = matches(item, filters);
      // The hidden property is the honest way to hide an element: it is
      // removed from the page for screen readers and keyboard users too,
      // which visibility or opacity would not do.
      item.card.hidden = !visible;
      if (visible) {
        shown += 1;
      }
    });

    countLine.textContent = shown === items.length
      ? shown + (shown === 1 ? " work" : " works")
      : "Showing " + shown + " of " + items.length + " works";

    emptyLine.hidden = shown !== 0;
  }

  // "input" fires on every keystroke, including paste and clearing the field.
  // No debounce is needed: nothing leaves the browser, so the only cost is a
  // loop over six items. Once this becomes a request per keystroke, that
  // changes completely.
  controls.q.addEventListener("input", apply);

  ["artist", "category", "status", "price"].forEach(function (name) {
    controls[name].addEventListener("change", apply);
  });

  // A type="reset" button restores the form defaults, but the browser does
  // that AFTER this event fires, so re-filter on the next tick.
  form.addEventListener("reset", function () {
    window.setTimeout(apply, 0);
  });

  // Nothing is submitted anywhere: there is no server endpoint behind this
  // form yet. Pressing Enter in the search box would otherwise reload the
  // page and appear to lose the filters.
  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });
})();
