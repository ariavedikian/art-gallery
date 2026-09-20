/*
  Filter form enhancement
  =======================

  The filtering itself is gone from this file. It now happens in SQL, and the
  filters live in the query string:

      /gallery?artist=artist-two&category=Print

  That is worth the round trip, because it buys three things the browser-only
  version could not have:

    * a filtered view has a URL, so it can be shared, bookmarked and reloaded
    * the server sends only matching rows, so the page does not grow with the
      collection, and it stays correct once there are more works than fit on
      one page
    * with JavaScript off, the form still submits and everything works

  All this file does now is press the button for you.
*/

(function () {
  "use strict";

  var form = document.getElementById("filters");
  if (!form) {
    return;
  }

  var submitButton = document.getElementById("filter-submit");
  var search = document.getElementById("filter-q");

  // Submitting reloads the page, so remember that we were the ones who did
  // it. Otherwise arriving from a shared link would steal focus and scroll
  // the visitor down to the filter bar uninvited.
  var FOCUS_KEY = "gallery-filter-focus";

  function remember(value) {
    // Private browsing and blocked storage make this throw rather than fail
    // quietly, and a focus nicety is never worth breaking the page over.
    try {
      if (value) {
        window.sessionStorage.setItem(FOCUS_KEY, "1");
      } else {
        window.sessionStorage.removeItem(FOCUS_KEY);
      }
    } catch (error) {
      /* storage unavailable: carry on without it */
    }
  }

  function wasOurSubmit() {
    try {
      return window.sessionStorage.getItem(FOCUS_KEY) === "1";
    } catch (error) {
      return false;
    }
  }

  function pruneEmptyFields() {
    // A form submits every named control, so unset filters would litter the
    // URL with q=&category=&status=&price=. A disabled control is not
    // submitted at all, so switching the empty ones off on the way out
    // leaves a clean, shareable ?artist=artist-two.
    //
    // The server ignores empty values either way, so this is cosmetic, and
    // it is exactly the kind of polish that belongs in an enhancement: with
    // JavaScript off the URL is uglier and the results are identical.
    Array.prototype.forEach.call(form.elements, function (field) {
      if (field.name && field.value === "") {
        field.disabled = true;
      }
    });
  }

  function submit() {
    remember(true);
    pruneEmptyFields();
    // requestSubmit behaves like a real button press, including validation.
    // submit() skips that, so it is only the fallback for older browsers.
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  // With JavaScript running, the Apply button is redundant. It stays in the
  // HTML because it is the whole no-JavaScript path; it is only hidden.
  if (submitButton) {
    submitButton.hidden = true;
  }

  // A menu choice is a finished decision, so submit straight away.
  Array.prototype.forEach.call(form.querySelectorAll("select"), function (select) {
    select.addEventListener("change", submit);
  });

  if (search) {
    // Typing is different: each keystroke could be a request and a query.
    // Typing "lithograph" would be eleven of each, ten of them already stale
    // before they came back — and replies can arrive out of order, so an
    // older result can overwrite a newer one.
    //
    // Debouncing: restart a 400ms timer on every keystroke and only submit
    // when it finally runs out. One request per pause in typing, not one per
    // letter. This is the cost of moving the work to the server, and the
    // reason the browser-only version needed nothing of the sort.
    var timer = null;

    search.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(submit, 400);
    });

    // After our own submit, put the caret back at the end of the search box
    // so typing can continue naturally across the reload.
    if (wasOurSubmit()) {
      remember(false);
      if (search.value) {
        search.focus();
        search.setSelectionRange(search.value.length, search.value.length);
      }
    }
  }

  // Leaving the page any other way should not arm the focus restore.
  form.addEventListener("reset", function () {
    remember(false);
  });
})();
