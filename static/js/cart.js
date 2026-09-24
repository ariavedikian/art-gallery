/*
  Add to cart, without leaving the page
  =====================================

  Without this file, the Add to cart form on an artwork page posts to
  /cart/add like any form: the browser leaves the page, the server answers
  with a redirect, and you land on the cart. That still works, and it is still
  what happens with JavaScript off.

  With this file, the same form is sent with fetch() to /api/cart instead. The
  server answers with JSON rather than a page, and this script uses it to
  update two things in place: the message under the button, and the count in
  the nav. You stay on the artwork you were looking at.

  Both routes call add_to_cart() in app.py, so the rules are the same either
  way. This file never decides what is allowed; it only reports what the
  server said.
*/

(function () {
  "use strict";

  var form = document.querySelector(".purchase__form[data-api]");
  if (!form) {
    return;   // not an artwork page, or not a work that can be bought
  }

  var status = document.getElementById("purchase-status");
  var badge = document.getElementById("cart-count");
  var badgeLabel = document.getElementById("cart-count-label");
  var button = form.querySelector('button[type="submit"]');

  function showMessage(text, isError, cartUrl) {
    status.textContent = text + " ";
    status.classList.toggle("purchase__status--error", Boolean(isError));

    // A link to the cart after a success, built as an element rather than by
    // pasting HTML into innerHTML. textContent can never be interpreted as
    // markup, so a message containing "<" is shown, not run.
    if (cartUrl) {
      var link = document.createElement("a");
      link.href = cartUrl;
      link.textContent = "View cart";
      status.appendChild(link);
    }
  }

  function updateBadge(count) {
    badge.textContent = count;
    badge.hidden = count === 0;
    badgeLabel.textContent = count
      ? " (" + count + (count === 1 ? " item)" : " items)")
      : "";
  }

  // async marks a function that can pause with await. fetch() does not return
  // the response -- the request takes time -- it returns a PROMISE of one.
  // await waits for that promise without freezing the page: scrolling,
  // clicking and everything else carry on while the request is in flight.
  async function send(event) {
    // Stop the browser posting the form itself. From here, we are the ones
    // sending it -- which is also why every failure below has to put things
    // right, since the browser is no longer going to.
    event.preventDefault();

    var quantityField = form.querySelector('input[name="quantity"]');
    var body = {
      artwork_id: Number(form.elements.artwork_id.value),
      // No quantity field on a unique original: there is only ever one.
      quantity: quantityField ? Number(quantityField.value) : 1
    };

    button.disabled = true;   // no double-adding by clicking twice quickly

    try {
      var response = await fetch(form.dataset.api, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify(body)
        // No credentials option needed: fetch sends cookies to its own site by
        // default, so the server finds the same session cart the page shows.
      });

      // fetch only REJECTS when the request never completed at all (network
      // down, server unreachable). A 404 or a 409 is a completed request
      // with a bad answer, so it arrives here, and response.ok -- true for
      // 200 to 299 -- is how the two are told apart.
      var data = await response.json();

      if (response.ok) {
        showMessage(data.message, false, data.cart_url);
        updateBadge(data.cart_count);
      } else {
        showMessage(data.error, true);
      }
    } catch (error) {
      // The request failed outright, or the answer was not JSON. Rather than
      // leave the visitor with a button that did nothing, fall back to the
      // way that works without JavaScript: post the form normally.
      //
      // form.submit() does NOT fire the submit event again, so this cannot
      // loop back into this function.
      form.submit();
      return;
    } finally {
      // finally runs whichever way the try block ended, so the button can
      // never be left stuck in its disabled state.
      button.disabled = false;
    }
  }

  form.addEventListener("submit", send);
})();
