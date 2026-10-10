"""
Shared plumbing for the tests.

Every test needs the same two things: a database that is not the one you are
working on, and a tidy way to report pass or fail. Both live here so no test
file carries its own copy of them.
"""

import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tests run as development, whatever the shell says, with a key of their own
# for this run -- so importing the app never writes instance/secret_key into
# the project, and never reads the one there.
os.environ["ART_GALLERY_ENV"] = "development"
os.environ["ART_GALLERY_SECRET_KEY"] = secrets.token_hex(32)

import app  # noqa: E402  (the path and environment must be set first)
from flask.testing import FlaskClient  # noqa: E402

DATABASE_DIR = PROJECT_ROOT / "database"

# Two seeds, answering two different questions. TEST_SEED is placeholder
# data the tests' expected values come from, and never changes with the
# content. SITE_SEED is what the site shows, and changes whenever the
# content does, so no test may take a value from it.
TEST_SEED = PROJECT_ROOT / "tests" / "seed.sql"
SITE_SEED = DATABASE_DIR / "seed.sql"


class PageClient(FlaskClient):
    """A test client that behaves like a browser on OUR pages.

    Every page with a form carries this session's CSRF token, and cart.js
    sends it as a header. A test is about the route it posts to, not about
    loading a page first, so this client does what a page would have done:
    it takes the session's token (making one if the session has none yet)
    and sends it as the X-CSRF-Token header with every POST.

    csrf=False sends the request WITHOUT it -- what another website's form
    would do. tests/test_csrf.py uses that, and checks the hidden fields in
    the real pages, which this client does not.
    """

    def open(self, *args, csrf=True, **kwargs):
        method = str(kwargs.get("method", "GET")).upper()
        if csrf and method not in app.SAFE_METHODS:
            # The same host as the request, so the right cookie is read.
            where = {"base_url": kwargs["base_url"]} if "base_url" in kwargs else {}
            with self.session_transaction(**where) as session:
                token = session.get(app.CSRF_KEY)
                if not token:
                    token = session[app.CSRF_KEY] = secrets.token_urlsafe(32)
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault(app.CSRF_HEADER, token)
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


app.app.test_client_class = PageClient


@contextmanager
def temp_database(seed=TEST_SEED):
    """Point the app at a throwaway database for the duration of the block.

    Built from the real schema.sql, so a test runs against the actual schema
    rather than a copy that can drift out of step with it. The DATA is the
    tests' own placeholder seed, TEST_SEED, whose values the tests depend
    on. A test checking a rule that every seed must obey can pass
    seed=SITE_SEED, to check the site's real content as well.

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
        connection.executescript(seed.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()

    app.DATABASE_PATH = path
    try:
        yield path
    finally:
        app.DATABASE_PATH = original
        shutil.rmtree(workspace, ignore_errors=True)


NOT_FOUND_PATH = "/no-such-page"


def get_page(client, path, results):
    """GET a page a test is about to inspect, and fail unless it IS that page.

    A test that sweeps a list of pages checks whatever comes back. If a path
    stops existing (a slug renamed, a route moved), the 404 page comes back
    instead, passes every check written for pages in general, and the page
    the sweep was written for is never looked at again -- while the test
    still prints PASS beside its address. So every page must answer 200,
    except NOT_FOUND_PATH, whose 404 is the point."""
    response = client.get(path)
    expected = 404 if path == NOT_FOUND_PATH else 200
    if response.status_code != expected:
        results.fail(f"{path} answered {response.status_code}, not {expected}:"
                     " the checks on it looked at the wrong page")
    return response


@contextmanager
def temp_folder():
    """A throwaway folder, deleted afterwards whatever happens."""
    folder = Path(tempfile.mkdtemp(prefix="art-gallery-files-"))
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


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


# The throwaway admin used by the tests. It only ever exists inside a temporary
# database that is deleted when the test finishes, so this is test data, not a
# credential for anything real.
TEST_ADMIN = "curator"
TEST_PASSWORD = "correct horse battery staple"


def create_admin(username=TEST_ADMIN, password=TEST_PASSWORD):
    """Create an admin in the current (temporary) database.

    Goes through the app's own set_admin_password(), so the hash is made
    exactly as `flask create-admin` makes it. app_context() provides the `g`
    that get_db() keeps its connection on, and closes it afterwards.
    """
    with app.app.app_context():
        app.set_admin_password(username, password)


def log_in(client, username=TEST_ADMIN, password=TEST_PASSWORD, next_url=""):
    """Post the login form, as a browser would. Returns the response."""
    return client.post("/admin/login", data={
        "username": username, "password": password, "next": next_url})
