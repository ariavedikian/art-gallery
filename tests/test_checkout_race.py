"""
Does checkout actually survive two people buying the same thing at once?

Run it:

    python tests/test_checkout_race.py

This is the one thing in the project a manual checklist cannot verify. Clicking
through the site by hand always does one thing at a time, so it can never
produce the situation Stage 12 was built for: two requests reaching the
inventory at the same instant. Only threads can.

What it proves, in both cases below, is that the database decides the winner:

    UPDATE artworks SET inventory_quantity = inventory_quantity - ?
     WHERE id = ? AND available_for_purchase = 1 AND inventory_quantity >= ?

The WHERE is the check and the SET is the claim, and nothing can happen between
them because there is no between. The losing threads get rowcount 0, raise
OutOfStock, and their transactions roll back.

A passing run is weaker evidence than a failing one: it shows the race did not
go wrong in these attempts, not that it never will. The real assurance is that
the statement is atomic by construction. This file exists to catch the day
somebody "simplifies" it into a SELECT and an UPDATE.
"""

import sys
import threading

from support import Results, direct_connection, buyer, temp_database

import app


def buy_together(artwork_id, quantity, buyers, results):
    """Send `buyers` simultaneous checkouts for the same work.

    Returns (orders_placed, turned_away).

    Each thread gets its own test client, so each has its own cart cookie and
    its own database connection -- the same separation two real visitors have.
    The Barrier is what makes this a race: every thread waits there, and they
    are all released at the same instant.
    """
    placed, refused = [], []
    at_the_gate = threading.Barrier(buyers)

    def one_buyer(number):
        client = app.app.test_client()
        with client.session_transaction() as session:
            session["cart"] = {str(artwork_id): quantity}

        at_the_gate.wait()
        try:
            response = client.post("/checkout", data=buyer(f"b{number}@example.com"))
        except Exception as error:          # noqa: BLE001 - any failure is a failure
            results.fail(f"buyer {number} raised {error!r}")
            return

        location = response.headers.get("Location", "")
        if location.startswith("/order/"):
            placed.append(number)
        elif response.status_code == 302:
            refused.append(number)
        else:
            # A 500 here would most likely be SQLite reporting a locked
            # database: the losing threads are supposed to be TURNED AWAY by
            # the WHERE clause, not to crash waiting for the write lock. If
            # they crashed, the queueing would be carrying this test and the
            # atomic claim would be doing nothing -- it would pass for the
            # wrong reason. So this counts as a failure, not as "no order".
            results.fail(f"buyer {number} got {response.status_code}")

    threads = [threading.Thread(target=one_buyer, args=(n,)) for n in range(buyers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return placed, refused


def read_state(artwork_id):
    with direct_connection() as connection:
        stock = connection.execute(
            "SELECT inventory_quantity FROM artworks WHERE id = ?",
            (artwork_id,)).fetchone()[0]
        orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        items = connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    return stock, orders, items


def unique_work_case(results):
    """Artwork 1 is a one-of-a-kind original. Five buyers, one painting."""
    print("  Five buyers, one unique original (artwork 1, stock 1)")

    placed, refused = buy_together(1, quantity=1, buyers=5, results=results)
    stock, orders, items = read_state(1)

    results.check("orders placed", len(placed), 1)
    results.check("buyers turned away", len(refused), 4)
    results.check("stock left", stock, 0)
    results.check("order rows", orders, 1)
    results.check("order_item rows", items, 1)


def edition_case(results):
    """Artwork 2 is an edition of 12. Five buyers want three each.

    Twelve divided by three is four, so exactly four can be satisfied and the
    fifth must be turned away. This is the case that earns its place: a naive
    `WHERE inventory_quantity > 0` passes the unique-work case above and sells
    thirteen prints out of twelve here.
    """
    print("  Five buyers wanting 3 each of an edition of 12 (artwork 2)")

    placed, refused = buy_together(2, quantity=3, buyers=5, results=results)
    stock, orders, _ = read_state(2)

    results.check("orders placed", len(placed), 4)
    results.check("buyers turned away", len(refused), 1)
    results.check("stock left", stock, 0)
    results.check("order rows", orders, 4)


def main():
    results = Results()

    for case in (unique_work_case, edition_case):
        # A fresh database per case, so one cannot affect another and either
        # can be read on its own.
        with temp_database():
            case(results)
        print()

    return results.report()


if __name__ == "__main__":
    # A non-zero exit code is what a CI runner reads, so this is usable
    # unchanged the day the project gets one.
    sys.exit(main())
