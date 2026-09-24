"""
Is an order really a record of the past, or does it quietly follow the present?

Run it:

    python tests/test_order_snapshot.py

order_items stores title_at_purchase, artist_at_purchase and unit_price_cents
alongside artwork_id. The artwork_id says WHICH work was bought; those three
columns say what it was called and what it cost at that moment.

The temptation is always to drop them and join to artworks instead -- it is
less to write, and it looks identical the day you write it. It stops looking
identical the first time a price changes, and by then every receipt ever
issued has silently changed with it. This file is what stands between the
design and that refactor.
"""

import sqlite3
import sys

from support import (Results, direct_connection, place_order, temp_database)

import app


def snapshot_survives_a_reprice(results):
    """Reprice and retitle the work; the receipt must not move."""
    print("  A sold work is repriced and retitled")

    client, reference = place_order(artwork_id=1)

    before = client.get(f"/order/{reference}").get_data(as_text=True)
    results.check("receipt shows the price paid", "$4,800" in before, True)

    with direct_connection() as connection:
        connection.execute("""
            UPDATE artworks
               SET price_cents = 9999900, title = 'A Completely New Title'
             WHERE id = 1
        """)
        connection.commit()

    after = client.get(f"/order/{reference}").get_data(as_text=True)

    results.check("total is unchanged", "$4,800" in after, True)
    results.check("new price does not appear", "$99,999" in after, False)
    results.check("old title is still on the receipt", "Artwork Title" in after, True)
    results.check("new title does not appear", "A Completely New Title" in after, False)

    # The stored total and the stored lines must agree with each other too. A
    # receipt whose lines do not add up to its total is worse than either one
    # being wrong on its own.
    with direct_connection() as connection:
        order = connection.execute(
            "SELECT id, subtotal_cents FROM orders WHERE reference = ?",
            (reference,)).fetchone()
        summed = connection.execute("""
            SELECT COALESCE(SUM(unit_price_cents * quantity), 0) AS total
              FROM order_items WHERE order_id = ?
        """, (order["id"],)).fetchone()["total"]

    results.check("stored total matches the stored lines",
                  summed, order["subtotal_cents"])


def a_sold_work_cannot_be_deleted(results):
    """ON DELETE RESTRICT: a sale is a fact about the past.

    This is the other half of the snapshot. The columns keep the receipt
    readable if the work changes; this keeps the link from dangling if someone
    tries to make the work disappear altogether.
    """
    print("  Deleting a work that has been sold")

    place_order(artwork_id=1)

    with direct_connection() as connection:
        try:
            connection.execute("DELETE FROM artworks WHERE id = 1")
            connection.commit()
            results.fail("the delete was allowed (foreign key not enforced?)")
        except sqlite3.IntegrityError:
            results.ok("refused by the foreign key, as intended")


def statuses_agree_with_the_database(results):
    """ORDER_STATUSES in app.py and the CHECK constraint must be the same list.

    Two places state the same rule, which is a thing this project usually
    refuses to allow. Here it is unavoidable -- SQLite cannot read a Python
    dict, and Python cannot see inside a CHECK -- so the next best thing is a
    test that fails the moment they disagree.
    """
    print("  The status vocabulary")

    with direct_connection() as connection:
        for status in app.ORDER_STATUSES:
            try:
                connection.execute("""
                    INSERT INTO orders (reference, customer_name, customer_email,
                                        shipping_address, subtotal_cents,
                                        payment_method, status, placed_at)
                    VALUES (?, 'n', 'e@example.com', 'a', 0, 'mock', ?, '2026-01-01T00:00:00+00:00')
                """, (f"ref-{status}", status))
            except sqlite3.IntegrityError:
                results.fail(f"the database rejected the known status {status!r}")
            else:
                results.ok(f"{status!r} is accepted")

        try:
            connection.execute("""
                INSERT INTO orders (reference, customer_name, customer_email,
                                    shipping_address, subtotal_cents,
                                    payment_method, status, placed_at)
                VALUES ('ref-bogus', 'n', 'e@example.com', 'a', 0, 'mock',
                        'definitely-not-a-status', '2026-01-01T00:00:00+00:00')
            """)
            results.fail("an unknown status was accepted")
        except sqlite3.IntegrityError:
            results.ok("an unknown status is refused by the CHECK constraint")


def remembered_orders_are_per_browser(results):
    """The orders list belongs to a browser, not to a person.

    Worth pinning down, because it is the honest limitation of having no
    accounts, and it is the sort of thing that could be "fixed" by accident
    into a real privacy bug.
    """
    print("  Remembered orders")

    buyer_client, reference = place_order(artwork_id=1)

    page = buyer_client.get("/orders").get_data(as_text=True)
    results.check("the buyer sees their order", reference in page, True)

    stranger = app.app.test_client()
    other_page = stranger.get("/orders").get_data(as_text=True)
    results.check("a different browser sees nothing", reference in other_page, False)
    results.check("and is told so", "has not placed an order yet" in other_page, True)

    # The reference itself is still the key to the order, from any browser.
    # That is by design: it is random, and it is what makes a shared link work.
    results.check("the reference still opens the order anywhere",
                  stranger.get(f"/order/{reference}").status_code, 200)


def main():
    results = Results()

    for case in (snapshot_survives_a_reprice,
                 a_sold_work_cannot_be_deleted,
                 statuses_agree_with_the_database,
                 remembered_orders_are_per_browser):
        # A fresh database per case, so one cannot affect another and any of
        # them can be read on its own.
        with temp_database():
            case(results)
        print()

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
