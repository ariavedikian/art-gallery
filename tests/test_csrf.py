"""
Does every request that changes something need this session's CSRF token?

Run it:

    python tests/test_csrf.py

For EVERY POST route in the app (found by walking the routing table, so a new
route cannot be forgotten), a request that would succeed is sent twice:

  without the token   as another website's form would send it: must be a 403,
                      and change nothing -- not the database, not the session
  with the token      as our own page sends it: must go through and change
                      something, which proves the 403 was about the token

Then the pages: every method="post" form on them carries the token, and no
GET form does.
"""

import logging
import re
import sys
from html.parser import HTMLParser

from flask.logging import default_handler

from support import (Results, buyer, create_admin, direct_connection, log_in,
                     place_order, temp_database)

import app

TABLES = ("artworks", "orders", "order_items", "admins")


def snapshot(client):
    """Everything a request could change: every row, and the session."""
    with direct_connection() as db:
        rows = {table: [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
                for table in TABLES}
    with client.session_transaction() as session:
        return rows, dict(session)


def admin_client():
    """A logged-in admin who has followed the login redirect, as a browser
    does. Otherwise "Logged in as curator." would still be waiting in the
    session, and the NEXT page -- even a refused one -- would show and clear
    it, which snapshot() would count as a change."""
    create_admin()
    client = app.app.test_client()
    log_in(client)
    client.get("/admin")
    return client


def artwork_form(artwork_id=None):
    """A valid artwork form: new, or the stored work's own values."""
    form = {"artist_id": "1", "title": "Artwork Title", "year": "2025",
            "medium": "Oil on Canvas", "category": "Painting",
            "description": "Placeholder description.", "price": "4800",
            "inventory_quantity": "1", "image": "placeholders/artwork-01.svg",
            "display_order": "100"}
    if artwork_id is not None:
        with direct_connection() as db:
            row = db.execute("SELECT image, inventory_quantity FROM artworks "
                             "WHERE id = ?", (artwork_id,)).fetchone()
        form.update(image=row["image"], inventory_quantity=str(row["inventory_quantity"]),
                    loaded_inventory=str(row["inventory_quantity"]),
                    title="Artwork Title, edited")
    return form


def in_cart(client, cart):
    with client.session_transaction() as session:
        session["cart"] = cart
    return client


# endpoint -> set up and return (client, path, keyword arguments for post()).
# Each makes a request that SUCCEEDS when the token is sent.
CASES = {
    "cart_add": lambda: (app.app.test_client(), "/cart/add", {"data": {"artwork_id": "2"}}),
    "cart_update": lambda: (in_cart(app.app.test_client(), {"2": 1}), "/cart/update",
                            {"data": {"artwork_id": "2", "quantity": "3"}}),
    "cart_remove": lambda: (in_cart(app.app.test_client(), {"2": 1}), "/cart/remove",
                            {"data": {"artwork_id": "2"}}),
    "checkout_submit": lambda: (in_cart(app.app.test_client(), {"2": 1}), "/checkout",
                                {"data": buyer()}),
    "api_cart_add": lambda: (app.app.test_client(), "/api/cart",
                             {"json": {"artwork_id": 2}}),
    "admin_login_submit": lambda: (create_admin() or app.app.test_client(), "/admin/login",
                                   {"data": {"username": "curator",
                                             "password": "correct horse battery staple"}}),
    "admin_logout": lambda: (admin_client(), "/admin/logout", {}),
    "admin_artwork_create": lambda: (admin_client(), "/admin/artworks/new",
                                     {"data": artwork_form()}),
    "admin_artwork_update": lambda: (admin_client(), "/admin/artworks/1/edit",
                                     {"data": artwork_form(1)}),
    "admin_artwork_delete": lambda: (admin_client(), "/admin/artworks/6/delete", {}),
    "admin_order_ship": lambda: (admin_client(),
                                 f"/admin/orders/{place_order(2)[1]}/ship", {}),
}


def every_post_route(results):
    print("  Every POST route: refused without the token, fine with it")
    posts = sorted(rule.endpoint for rule in app.app.url_map.iter_rules()
                   if "POST" in rule.methods)
    results.check("every POST route has a case here", sorted(set(posts) - set(CASES)), [])

    for endpoint in posts:
        if endpoint not in CASES:
            continue
        with temp_database():
            client, path, kwargs = CASES[endpoint]()
            before = snapshot(client)

            refused = client.post(path, csrf=False, **kwargs)
            results.check(f"{endpoint}: without the token", refused.status_code, 403)
            results.check(f"{endpoint}: ...changed nothing", snapshot(client) == before, True)
            if path.startswith("/api/"):
                results.check(f"{endpoint}: ...and says why, in JSON",
                              "error" in (refused.get_json() or {}), True)

            accepted = client.post(path, **kwargs)
            results.check(f"{endpoint}: with the token it goes through",
                          accepted.status_code in (200, 302), True)
            results.check(f"{endpoint}: ...and changes something",
                          snapshot(client) != before, True)


def wrong_tokens(results):
    print("  Only THIS session's token will do")
    visitor = in_cart(app.app.test_client(), {"2": 1})
    visitor.get("/cart")                  # the page makes the token
    with visitor.session_transaction() as session:
        token = session[app.CSRF_KEY]

    stranger = app.app.test_client()
    stranger.get("/artwork/2")
    with stranger.session_transaction() as session:
        strangers_token = session[app.CSRF_KEY]
    results.check("two sessions get two different tokens", token != strangers_token, True)

    for label, sent in (("another session's (valid) token", strangers_token),
                        ("a token one character off", token[:-1] + ("A" if token[-1] != "A" else "B")),
                        ("an empty token", ""),
                        ("a non-ASCII token", "é" * len(token))):
        response = visitor.post("/cart/remove", csrf=False,
                                data={"artwork_id": "2", app.CSRF_FIELD: sent})
        results.check(f"{label}: refused, not a crash", response.status_code, 403)

    response = visitor.post("/cart/remove", csrf=False,
                            data={"artwork_id": "2", app.CSRF_FIELD: token})
    results.check("the right token in the hidden FIELD (as the forms send it)",
                  response.status_code, 302)

    visitor.get("/cart")
    with visitor.session_transaction() as session:
        results.check("the token stays the same across pages (tabs keep working)",
                      session[app.CSRF_KEY], token)

    response = app.app.test_client().post("/cart/add", csrf=False,
                                          data={"artwork_id": "2"})
    page = response.get_data(as_text=True)
    results.check("a refused form explains itself", "form has expired" in page, True)


class Forms(HTMLParser):
    """Every form on a page: its method, and the csrf_token values inside it."""

    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.forms.append({"method": (attrs.get("method") or "get").lower(),
                               "action": attrs.get("action"), "tokens": []})
        elif tag == "input" and attrs.get("name") == app.CSRF_FIELD and self.forms:
            self.forms[-1]["tokens"].append(attrs.get("value"))


def pages_carry_the_token(results):
    print("  Every POST form on every page carries the token; no GET form does")
    admin = admin_client()
    place_order(2)                            # a paid order: the Ship form
    in_cart(admin, {"2": 1, "1": 1})          # cart lines: update and remove

    pages = {path: admin for path in (
        "/artwork/2", "/cart", "/checkout", "/gallery", "/admin", "/admin/orders",
        "/admin/artworks/new", "/admin/artworks/1/edit", "/admin/artworks/6/delete")}
    pages["/admin/login"] = app.app.test_client()

    actions = set()
    for path, client in pages.items():
        html = client.get(path).get_data(as_text=True)
        with client.session_transaction() as session:
            token = session.get(app.CSRF_KEY)
        for form in Forms(html).forms:
            where = f"{path}: {form['method'].upper()} form to {form['action']}"
            if form["method"] == "post":
                actions.add(re.sub(r"/\d+|/orders/[^/]+", "/<id>", form["action"]))
                results.check(f"{where} carries this session's token",
                              form["tokens"], [token])
            else:
                results.check(f"{where} carries no token", form["tokens"], [])

    # Not a vacuous pass: the pages above hold every kind of POST form -- nine
    # forms in the templates, one of which (the artwork form) posts to two
    # places, new and edit: ten actions, one per POST route but the API's.
    results.check("kinds of POST form checked", len(actions), 10)


class Collected(logging.Handler):
    """The app's log lines, kept here instead of printed over the results."""

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def main():
    results = Results()
    log = Collected()
    app.app.logger.removeHandler(default_handler)
    app.app.logger.addHandler(log)

    every_post_route(results)
    print()
    for case in (wrong_tokens, pages_carry_the_token):
        with temp_database():
            case(results)
        print()

    # A refusal is logged, so a burst of them in a real server's log (someone
    # trying) can be seen. 11 routes refused once each, plus 5 in wrong_tokens.
    refusals = [m for m in log.messages if m.startswith("CSRF check failed")]
    results.check("every refusal was logged", len(refusals), len(CASES) + 5)
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
