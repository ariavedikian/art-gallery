"""
Does the admin CMS change the collection correctly -- and refuse to when it should?

Run it:

    python tests/test_cms.py

Whether these routes are LOCKED is test_admin.py's job: it walks the routing
table, so it already covers every route added here. This file is about what
the routes do once an admin is in.
"""

import re
import sys

from support import (Results, create_admin, direct_connection, log_in,
                     place_order, temp_database)

import app

# A complete, valid form. Each test copies it and breaks one thing.
GOOD_FORM = {
    "artist_id": "1",
    "title": "New Placeholder Work",
    "year": "2025",
    "medium": "Oil on Canvas",
    "category": "Painting",
    "description": "Placeholder artwork description.",
    "price": "$4,800.50",
    "inventory_quantity": "1",
    "available_for_purchase": "1",
    "image": "placeholders/artwork-01.svg",
    "image_width": "900",
    "image_height": "1100",
    "display_order": "15",
}


def admin_client():
    create_admin()
    client = app.app.test_client()
    log_in(client)
    return client


def artwork_row(artwork_id):
    with direct_connection() as connection:
        return connection.execute("SELECT * FROM artworks WHERE id = ?",
                                  (artwork_id,)).fetchone()


def count_artworks():
    with direct_connection() as connection:
        return connection.execute("SELECT COUNT(*) FROM artworks").fetchone()[0]


def creating(results):
    print("  Adding an artwork")
    client = admin_client()

    response = client.post("/admin/artworks/new", data=GOOD_FORM)
    results.check("a valid form redirects", response.status_code, 302)
    results.check("a seventh work exists", count_artworks(), 7)

    row = artwork_row(7)
    results.check("the price was stored exactly, in cents", row["price_cents"], 480050)
    results.check("the ticked box became 1", row["available_for_purchase"], 1)
    results.check("the UNticked box (absent from the form) became 0", row["is_featured"], 0)

    # It is a real artwork now: the public site and the API both see it.
    results.check("its public page exists", client.get("/artwork/7").status_code, 200)
    api = client.get("/api/artworks/7").get_json()
    results.check("the API reports its price", api["price_cents"], 480050)

    # display_order 15 slots it between 10 and 20: second in the running order.
    order = [art["id"] for art in client.get("/api/artworks").get_json()["artworks"]]
    results.check("it hangs where display_order put it", order[1], 7)

    blank_year = dict(GOOD_FORM, year="")
    client.post("/admin/artworks/new", data=blank_year)
    results.check("a blank date is stored as NULL (unknown), not ''",
                  artwork_row(8)["year"], None)


def money(results):
    """Every price goes through Decimal. This is the float trap, pinned down."""
    print("  Prices typed by a person")
    cases = {
        "4800": 480000, "4,800": 480000, "$4,800.50": 480050, "0": 0,
        # float("19.99") * 100 is 1998.9999999999998 -- int() of that is a
        # cent short. These are the values a float-based form gets wrong.
        "19.99": 1999, "1.15": 115, "0.29": 29,
    }
    for text, cents in cases.items():
        results.check(f"{text!r} -> cents", app.parse_price(text), cents)

    for text in ("12.345", "-5", "1e5", "abc", "", "4 800"):
        results.check(f"{text!r} is refused", app.parse_price(text), None)

    results.check("a stored price goes back into the form without a float",
                  app.price_for_input(1999), "19.99")


def validation(results):
    print("  A bad form is refused, and nothing is written")
    client = admin_client()

    bad = {
        "title": "",                                   # required
        "price": "12.345",                             # three decimals
        "inventory_quantity": "-1",                    # negative
        "artist_id": "999",                            # no such artist
        "image": "../../app.py",                       # not an offered image
        "image_width": "0",                            # out of range
    }
    for field, value in bad.items():
        response = client.post("/admin/artworks/new", data=dict(GOOD_FORM, **{field: value}))
        html = response.get_data(as_text=True)
        results.check(f"bad {field} ({value!r}) is a 400", response.status_code, 400)
        results.check(f"...with an error on {field}",
                      f'id="error-{field}"' in html, True)

    results.check("no artwork was created by any of them", count_artworks(), 6)

    # What was typed survives the round trip, so nothing has to be retyped.
    response = client.post("/admin/artworks/new", data=dict(GOOD_FORM, price="oops"))
    html = response.get_data(as_text=True)
    results.check("the title typed is still in the form",
                  'value="New Placeholder Work"' in html, True)
    results.check("the bad price is shown back, to be corrected",
                  'value="oops"' in html, True)


def editing(results):
    print("  Editing an artwork")
    client = admin_client()

    form = client.get("/admin/artworks/2/edit").get_data(as_text=True)
    loaded = re.search(r'name="loaded_inventory" value="(\d+)"', form).group(1)

    edit = dict(GOOD_FORM, artist_id="2", title="Retitled Print", price="1,300",
                inventory_quantity="12", loaded_inventory=loaded,
                image="placeholders/artwork-02.svg", image_width="1000",
                image_height="800", display_order="20")
    response = client.post("/admin/artworks/2/edit", data=edit)
    results.check("a valid edit redirects", response.status_code, 302)

    row = artwork_row(2)
    results.check("the new price is stored", row["price_cents"], 130000)
    results.check("the new title is stored", row["title"], "Retitled Print")

    results.check("an unknown artwork is a 404",
                  client.post("/admin/artworks/999/edit", data=edit).status_code, 404)


def lost_update(results):
    """A sale while the form is open must not be overwritten by the form."""
    print("  A sale while the edit form is open")
    client = admin_client()

    # The admin opens the form: stock 12.
    form = client.get("/admin/artworks/2/edit").get_data(as_text=True)
    loaded = re.search(r'name="loaded_inventory" value="(\d+)"', form).group(1)
    results.check("the form loaded stock", loaded, "12")

    # Meanwhile, a visitor buys three. Stock is now 9.
    place_order(artwork_id=2, quantity=3)
    results.check("the sale happened", artwork_row(2)["inventory_quantity"], 9)

    # The admin saves the form, which still says 12, having fixed a typo.
    edit = dict(GOOD_FORM, artist_id="2", title="Artwork Title",
                description="Fixed a typo.", price="1250",
                inventory_quantity="12", loaded_inventory=loaded,
                image="placeholders/artwork-02.svg", image_width="1000",
                image_height="800", display_order="20")
    response = client.post("/admin/artworks/2/edit", data=edit)
    html = response.get_data(as_text=True)

    results.check("the save is refused as a conflict (409)", response.status_code, 409)
    results.check("the sale was NOT overwritten", artwork_row(2)["inventory_quantity"], 9)
    results.check("the description was not half-saved either",
                  artwork_row(2)["description"], "Placeholder artwork description.")
    results.check("the form explains what changed",
                  "Stock changed from 12 to 9" in html, True)
    results.check("the form now shows the real stock", 'value="9"' in html, True)
    results.check("...and the typo fix is still in the form, not lost",
                  "Fixed a typo." in html, True)

    # Saving again, now from the current number, works.
    retry = dict(edit, inventory_quantity="9", loaded_inventory="9")
    results.check("saving again from the fresh number works",
                  client.post("/admin/artworks/2/edit", data=retry).status_code, 302)
    results.check("...and the typo fix is saved", artwork_row(2)["description"], "Fixed a typo.")


def deleting(results):
    print("  Deleting")
    client = admin_client()

    confirm = client.get("/admin/artworks/6/delete")
    results.check("the confirmation page opens", confirm.status_code, 200)
    results.check("...and opening it deleted nothing", count_artworks(), 6)

    response = client.post("/admin/artworks/6/delete")
    results.check("the POST deletes", response.status_code, 302)
    results.check("the work is gone", artwork_row(6), None)
    results.check("its public page is now a 404", client.get("/artwork/6").status_code, 404)

    # A sold work: the database's foreign key refuses, and we explain.
    place_order(artwork_id=1)
    page = client.get("/admin/artworks/1/delete").get_data(as_text=True)
    results.check("the confirmation page warns that it has been sold",
                  "cannot be deleted" in page, True)
    results.check("...and offers no delete button",
                  "Delete permanently" in page, False)

    # Even when the POST is sent anyway, the database refuses.
    response = client.post("/admin/artworks/1/delete")
    results.check("a forced delete is turned away", response.status_code, 302)
    results.check("the sold work is still there", artwork_row(1) is not None, True)


def shipping(results):
    print("  Marking orders shipped")
    client = admin_client()
    _, reference = place_order(artwork_id=2)

    def status():
        with direct_connection() as connection:
            return connection.execute("SELECT status FROM orders WHERE reference = ?",
                                      (reference,)).fetchone()[0]

    page = client.get("/admin/orders").get_data(as_text=True)
    results.check("the order is listed", reference in page, True)
    results.check("a paid order offers Mark shipped", "Mark shipped" in page, True)

    client.post(f"/admin/orders/{reference}/ship")
    results.check("paid -> shipped", status(), "shipped")

    # A double-click, or a second tab: the WHERE clause refuses the repeat.
    client.post(f"/admin/orders/{reference}/ship")
    results.check("shipping again changes nothing", status(), "shipped")
    results.check("a shipped order no longer offers the button",
                  "Mark shipped" in client.get("/admin/orders").get_data(as_text=True), False)

    # Only paid orders may be shipped. Force one to 'pending' and try.
    with direct_connection() as connection:
        connection.execute("UPDATE orders SET status = 'pending' WHERE reference = ?",
                           (reference,))
        connection.commit()
    client.post(f"/admin/orders/{reference}/ship")
    results.check("a pending order cannot be shipped", status(), "pending")

    results.check("an unknown order is a 404",
                  client.post("/admin/orders/no-such-order/ship").status_code, 404)


def main():
    results = Results()

    for case in (creating, money, validation, editing, lost_update, deleting,
                 shipping):
        with temp_database():
            case(results)
        print()

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
