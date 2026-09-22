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

Nothing here touches database/art_gallery.db. The test builds its own database
in a temporary folder from schema.sql and seed.sql, and deletes it afterwards.
A test that can destroy the data you are working on is worse than no test.
"""

import shutil
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app  # noqa: E402  (the path has to be set before this import)

DATABASE_DIR = PROJECT_ROOT / "database"

BUYER = {
    "customer_name": "Buyer",
    "shipping_address": "1 Placeholder Street",
    "mock_payment": "approve",
}


def build_temp_database(directory):
    """A fresh database from the real schema and seed files.

    The same two files init_db.py uses, so the test runs against the actual
    schema rather than a copy that can drift out of step with it.
    """
    path = Path(directory) / "test.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript((DATABASE_DIR / "schema.sql").read_text(encoding="utf-8"))
        connection.executescript((DATABASE_DIR / "seed.sql").read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()
    return path


def buy_together(artwork_id, quantity, buyers):
    """Send `buyers` simultaneous checkouts for the same work.

    Returns (orders_placed, turned_away, errors).

    Each thread gets its own test client, so each has its own cart cookie and
    its own database connection — the same separation two real visitors have.
    The Barrier is what makes this a race: every thread waits there, and they
    are all released at the same instant.
    """
    placed, refused, errors = [], [], []
    at_the_gate = threading.Barrier(buyers)

    def one_buyer(number):
        client = app.app.test_client()
        with client.session_transaction() as session:
            session["cart"] = {str(artwork_id): quantity}

        at_the_gate.wait()
        try:
            response = client.post("/checkout",
                                   data={**BUYER, "customer_email": f"b{number}@example.com"})
        except Exception as error:          # noqa: BLE001 - the test wants any failure
            errors.append(f"buyer {number} raised {error!r}")
            return

        location = response.headers.get("Location", "")
        if location.startswith("/order/"):
            placed.append(number)
        elif response.status_code == 302:
            refused.append(number)
        else:
            # A 500 here would most likely be SQLite reporting a locked
            # database: the losing threads are supposed to be TURNED AWAY by
            # the WHERE clause, not to crash waiting for the write lock.
            errors.append(f"buyer {number} got {response.status_code}")

    threads = [threading.Thread(target=one_buyer, args=(n,)) for n in range(buyers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return placed, refused, errors


def read_state(artwork_id):
    connection = sqlite3.connect(app.DATABASE_PATH)
    try:
        stock = connection.execute(
            "SELECT inventory_quantity FROM artworks WHERE id = ?",
            (artwork_id,)).fetchone()[0]
        orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        items = connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
    finally:
        connection.close()
    return stock, orders, items


def check(description, actual, expected):
    ok = actual == expected
    print(f"    {'PASS' if ok else 'FAIL'}  {description}: {actual!r}"
          f"{'' if ok else f' (expected {expected!r})'}")
    return ok


def unique_work_case():
    """Artwork 1 is a one-of-a-kind original. Five buyers, one painting."""
    print("  Five buyers, one unique original (artwork 1, stock 1)")

    placed, refused, errors = buy_together(artwork_id=1, quantity=1, buyers=5)
    stock, orders, items = read_state(1)

    for message in errors:
        print(f"    FAIL  {message}")

    return all([
        not errors,
        check("orders placed", len(placed), 1),
        check("buyers turned away", len(refused), 4),
        check("stock left", stock, 0),
        check("order rows", orders, 1),
        check("order_item rows", items, 1),
    ])


def edition_case():
    """Artwork 2 is an edition of 12. Five buyers want three each.

    Twelve divided by three is four, so exactly four can be satisfied and the
    fifth must be turned away — the quantity has to be respected, not just the
    fact that SOME stock exists.
    """
    print("  Five buyers wanting 3 each of an edition of 12 (artwork 2)")

    placed, refused, errors = buy_together(artwork_id=2, quantity=3, buyers=5)
    stock, orders, items = read_state(2)

    for message in errors:
        print(f"    FAIL  {message}")

    return all([
        not errors,
        check("orders placed", len(placed), 4),
        check("buyers turned away", len(refused), 1),
        check("stock left", stock, 0),
        check("order rows", orders, 4),
    ])


def main():
    workspace = tempfile.mkdtemp(prefix="art-gallery-test-")
    real_database = app.DATABASE_PATH

    try:
        # Point the app at the throwaway database. get_db() reads this at call
        # time rather than at import, so reassigning it is enough.
        app.DATABASE_PATH = build_temp_database(workspace)
        print(f"Using a temporary database: {app.DATABASE_PATH}\n")

        results = [unique_work_case()]
        print()

        # A fresh database for the second case, so the two cannot affect each
        # other and either can be read on its own.
        shutil.rmtree(workspace)
        workspace = tempfile.mkdtemp(prefix="art-gallery-test-")
        app.DATABASE_PATH = build_temp_database(workspace)

        results.append(edition_case())
    finally:
        app.DATABASE_PATH = real_database
        shutil.rmtree(workspace, ignore_errors=True)

    print()
    if all(results):
        print("All checks passed. The real database was never touched.")
        return 0

    print("FAILURES above. The real database was never touched.")
    return 1


if __name__ == "__main__":
    # A non-zero exit code is what a CI runner reads, so this is usable
    # unchanged the day the project gets one.
    sys.exit(main())
