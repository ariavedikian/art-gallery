"""
Shared plumbing for the tests.

Every test needs the same two things: a database that is not the one you are
working on, and a tidy way to report pass or fail. Both live here so no test
file carries its own copy of them.
"""

import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app  # noqa: E402  (the path has to be set before this import)

DATABASE_DIR = PROJECT_ROOT / "database"


@contextmanager
def temp_database():
    """Point the app at a throwaway database for the duration of the block.

    Built from the real schema.sql and seed.sql, so a test runs against the
    actual schema rather than a copy that can drift out of step with it.

    get_db() reads app.DATABASE_PATH when it is called rather than at import
    time, so reassigning the module attribute is enough to redirect the whole
    application. The finally block puts it back whatever happens, so a failing
    test cannot leave the app pointed at a deleted file.
    """
    workspace = tempfile.mkdtemp(prefix="art-gallery-test-")
    path = Path(workspace) / "test.db"
    original = app.DATABASE_PATH

    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript((DATABASE_DIR / "schema.sql").read_text(encoding="utf-8"))
        connection.executescript((DATABASE_DIR / "seed.sql").read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()

    app.DATABASE_PATH = path
    try:
        yield path
    finally:
        app.DATABASE_PATH = original
        shutil.rmtree(workspace, ignore_errors=True)


@contextmanager
def direct_connection():
    """A connection of our own, for setting up and inspecting state.

    Deliberately separate from the app's own connection: a test that checks
    the database through the same code path it is testing can agree with a
    bug rather than catch it.
    """
    connection = sqlite3.connect(app.DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


class Results:
    """A running tally, so a test file can report every failure rather than
    stopping at the first one. Seeing all three things that broke is more
    useful than seeing the first and guessing."""

    def __init__(self):
        self.failures = 0

    def check(self, description, actual, expected):
        ok = actual == expected
        if not ok:
            self.failures += 1
        print(f"    {'PASS' if ok else 'FAIL'}  {description}: {actual!r}"
              f"{'' if ok else f' (expected {expected!r})'}")
        return ok

    def ok(self, description):
        print(f"    PASS  {description}")

    def fail(self, description):
        self.failures += 1
        print(f"    FAIL  {description}")

    def report(self):
        print()
        if self.failures:
            print(f"{self.failures} check(s) FAILED. The real database was never touched.")
            return 1
        print("All checks passed. The real database was never touched.")
        return 0


def buyer(email="buyer@example.com"):
    """The form fields a successful checkout needs."""
    return {
        "customer_name": "Buyer",
        "customer_email": email,
        "shipping_address": "1 Placeholder Street",
        "mock_payment": "approve",
    }


def place_order(artwork_id, quantity=1):
    """Run a real checkout through the app and return (client, reference).

    Goes through the HTTP routes rather than calling place_order() directly,
    so the test exercises what a visitor actually triggers.
    """
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["cart"] = {str(artwork_id): quantity}

    response = client.post("/checkout", data=buyer())
    location = response.headers.get("Location", "")
    if not location.startswith("/order/"):
        raise AssertionError(f"checkout did not place an order: {location!r}")

    return client, location.rsplit("/", 1)[-1]
