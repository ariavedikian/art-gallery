"""
Does the JSON API keep its promises?

Run it:

    python tests/test_api.py

An API is a contract with code you may never see, so this file checks the
contract rather than the pages: the status codes, the shape of the JSON, and
that the business rules the pages enforce are enforced here too.
"""

import sys

from support import Results, temp_database

import app


def get_json(client, path):
    response = client.get(path)
    return response, response.get_json()


def post_json(client, body):
    response = client.post("/api/cart", json=body)
    return response, response.get_json()


def collection(results):
    print("  GET /api/artworks")
    client = app.app.test_client()

    response, data = get_json(client, "/api/artworks")
    results.check("status", response.status_code, 200)
    results.check("content type is JSON", response.mimetype, "application/json")
    results.check("every work is listed", data["count"], 6)
    results.check("count matches the list", len(data["artworks"]), data["count"])

    # The contract: exactly these fields, no more. A column added to the
    # database must not quietly appear in the API.
    results.check("fields are exactly the promised ones",
                  sorted(data["artworks"][0]),
                  sorted(["id", "title", "artist", "year", "medium", "category",
                          "description", "status", "price_cents",
                          "available_quantity", "image", "url"]))

    # Same order as the All works page: both come from search_artworks().
    ids = [art["id"] for art in data["artworks"]]
    results.check("gallery running order (display_order)", ids, [4, 2, 5, 1, 3, 6])

    _, sold = get_json(client, "/api/artworks?status=sold")
    results.check("the same filters as the page work",
                  [art["id"] for art in sold["artworks"]], [3])

    _, junk = get_json(client, "/api/artworks?price=not-a-range")
    results.check("an unknown filter value is ignored, as on the page",
                  junk["count"], 6)


def business_rules(results):
    print("  Prices follow the same rules as the page")
    client = app.app.test_client()

    _, for_sale = get_json(client, "/api/artworks/1")
    results.check("a work for sale shows its price", for_sale["price_cents"], 480000)

    _, not_for_sale = get_json(client, "/api/artworks/5")
    results.check("a work not for sale shows NO price", not_for_sale["price_cents"], None)
    results.check("...and nothing available", not_for_sale["available_quantity"], 0)

    _, sold = get_json(client, "/api/artworks/3")
    results.check("a sold work shows no price", sold["price_cents"], None)

    results.check("URLs are absolute, for readers with no page to be relative to",
                  for_sale["url"].startswith("http"), True)


def errors(results):
    print("  Errors are JSON, with honest status codes")
    client = app.app.test_client()

    response, data = get_json(client, "/api/artworks/999")
    results.check("unknown artwork is 404", response.status_code, 404)
    results.check("...with a JSON error", "error" in data, True)

    response, data = get_json(client, "/api/nothing-here")
    results.check("unknown API path is 404", response.status_code, 404)
    results.check("...as JSON, not the HTML 404 page", data is not None, True)

    response = client.get("/api/cart")
    results.check("wrong method is 405", response.status_code, 405)
    results.check("...and says which method would work",
                  "POST" in response.headers.get("Allow", ""), True)

    # The HTML site keeps its HTML 404 page.
    response = client.get("/nothing-here")
    results.check("outside /api/ a 404 is still HTML", response.mimetype, "text/html")


def cart(results):
    print("  POST /api/cart")
    client = app.app.test_client()

    response, data = post_json(client, {"artwork_id": 2, "quantity": 3})
    results.check("adding works", response.status_code, 200)
    results.check("outcome", data["outcome"], "added")
    results.check("cart count comes back", data["cart_count"], 3)

    # It is the real session cart: the HTML cart page sees it too.
    with client.session_transaction() as session:
        results.check("the session cart holds it", session.get("cart"), {"2": 3})

    response, data = post_json(client, {"artwork_id": 2, "quantity": 50})
    results.check("too many is capped, not refused", data["outcome"], "capped")
    results.check("...to the per-line limit", data["quantity_in_cart"], 10)

    response, data = post_json(client, {"artwork_id": 3})
    results.check("a sold work is refused with 409", response.status_code, 409)

    response, data = post_json(client, {"artwork_id": 5})
    results.check("a work not for sale is refused with 409", response.status_code, 409)

    response, _ = post_json(client, {"artwork_id": 999})
    results.check("an unknown work is 404", response.status_code, 404)


def bad_input(results):
    print("  Malformed requests are 400, never 500")
    client = app.app.test_client()

    response, _ = post_json(client, {"artwork_id": "2"})
    results.check('"2" (a string) is not 2', response.status_code, 400)

    response, _ = post_json(client, {"artwork_id": True})
    results.check("true is not 1, even though Python thinks it is",
                  response.status_code, 400)

    response, _ = post_json(client, {"artwork_id": 2, "quantity": 1.5})
    results.check("1.5 is not a quantity", response.status_code, 400)

    response, _ = post_json(client, ["artwork_id", 2])
    results.check("a list is not an object", response.status_code, 400)

    # A plain form post, as another website's <form> could send. No JSON
    # label, so the API refuses it outright.
    response = client.post("/api/cart", data={"artwork_id": "2"})
    results.check("a form-encoded body is refused", response.status_code, 400)

    response = client.post("/api/cart", data="{not json",
                           content_type="application/json")
    results.check("broken JSON is refused", response.status_code, 400)


def one_rule_two_routes(results):
    """The HTML form and the API must agree, because they share add_to_cart()."""
    print("  The form route and the API apply the same rules")

    form_client = app.app.test_client()
    form_client.post("/cart/add", data={"artwork_id": 2, "quantity": 50})

    api_client = app.app.test_client()
    post_json(api_client, {"artwork_id": 2, "quantity": 50})

    with form_client.session_transaction() as session:
        via_form = session.get("cart")
    with api_client.session_transaction() as session:
        via_api = session.get("cart")

    results.check("same cart either way", via_api, via_form)


def main():
    results = Results()

    for case in (collection, business_rules, errors, cart, bad_input,
                 one_rule_two_routes):
        with temp_database():
            case(results)
        print()

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
