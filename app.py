"""
Art Gallery — a Flask web application.

Stage 16 (part 1): admin accounts and a locked admin area.

HTTP is stateless — two requests from the same visitor arrive as strangers —
so a cart has to be stored somewhere and handed back with every request. This
one lives in the Flask session: a cookie in the visitor's browser, signed with
SECRET_KEY so it cannot be edited without the signature failing.

The cookie holds one thing: {artwork_id: quantity}. Titles, prices and
availability are read from the database on every request, so a price can never
arrive from the client.

Checkout turns that cart into an order inside a single transaction: the
inventory is claimed and the order is written together, or neither happens.
The payment step is a clearly-labelled MOCK until Stage 14 (deferred).

Under /api/ the same data is served as JSON rather than HTML. Those routes
call the same data-access functions as the pages, so a rule written once --
the filters, the `status` rule, the cart limits -- serves both.

Under /admin/ is the gallery's private area. Admins are rows in the admins
table holding a password HASH, never a password; the first one is created
from the terminal with `flask --app app create-admin <name>`.
"""

import functools
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import click
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

GALLERY_NAME = "Gallery Placeholder"

# The key Flask uses to SIGN the session cookie. Signing is not encryption:
# the visitor can read what is in their cookie, they simply cannot change it
# without the signature failing and Flask throwing the whole cookie away.
#
# In development this falls back to a fixed string so the app runs out of the
# box. A real deployment sets ART_GALLERY_SECRET_KEY to a long random value
# and never commits it; Stage 20 comes back to this properly.
app.secret_key = os.environ.get("ART_GALLERY_SECRET_KEY", "dev-key-not-a-secret")

# Now that the session cookie can prove someone is an ADMIN, how it travels
# matters. SameSite=Lax tells the browser not to send it along with a POST
# that starts on another website. Without that, a page elsewhere could hold a
# hidden form that posts to /admin/... and the admin's own browser would
# helpfully attach their login. Modern browsers already default to Lax;
# saying it explicitly means we rely on our code, not on their defaults.
# (The full defence against cross-site requests is Stage 20.)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Built from database/schema.sql + seed.sql by: python init_db.py --reset
DATABASE_PATH = Path(__file__).resolve().parent / "database" / "art_gallery.db"


# --- Database plumbing -------------------------------------------------------

def get_db():
    """Return this request's database connection, opening one if needed.

    `g` is Flask's per-request scratchpad: a fresh, private object for every
    request, discarded when the request ends. Keeping the connection there
    means one connection per request, shared by every query within it and
    never shared between two visitors.
    """
    if "db" not in g:
        if not DATABASE_PATH.exists():
            raise RuntimeError(
                f"No database at {DATABASE_PATH}. Run: python init_db.py"
            )

        # isolation_level=None turns OFF Python's habit of opening and
        # committing transactions for you. By default the sqlite3 module
        # silently BEGINs before an INSERT or UPDATE — but not before a
        # SELECT — and commits at times that are easy to get wrong.
        #
        # Checkout needs a SELECT and several writes inside ONE transaction
        # whose boundaries we chose, so from here on transactions are explicit:
        # see place_order(). Every other query in this file is a plain read and
        # is unaffected.
        g.db = sqlite3.connect(DATABASE_PATH, isolation_level=None)

        # Without this, a row is a plain tuple: row[0], row[1], ...
        # sqlite3.Row allows row["title"], which is exactly what the templates
        # already write as {{ art.title }}. One line, and the templates that
        # were built against Python dicts keep working untouched.
        g.db.row_factory = sqlite3.Row

        # SQLite ignores foreign keys unless asked, on EVERY connection.
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """Close the connection when the request ends.

    Flask calls this after every request, whether it succeeded or raised.
    An open connection holds a file handle and a lock; leaking one per
    request would eventually bring the server down.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_db(sql, params=(), one=False):
    """Run a SELECT and return a list of rows, or a single row with one=True.

    `params` supplies the values for the ? placeholders in `sql`.
    """
    cursor = get_db().execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return (rows[0] if rows else None) if one else rows


# --- Data access -------------------------------------------------------------
# Same function names and same return shapes as Stage 4. Only the bodies moved
# from Python loops to SQL.

# Listing columns explicitly, rather than SELECT *, means a later schema change
# cannot silently alter what the templates receive. This string is written by
# us and never contains user input, so it is safe to paste into a query;
# VALUES from a visitor never are. See get_artist below.
# The three availability states, written once as a SQL expression and used
# twice: to give every artwork a `status` column, and in the WHERE clause when
# someone filters by availability. The same rule used to live in a Jinja macro
# as well. Now the database derives it and the templates just read it.
_STATUS_CASE = """
    CASE
        WHEN aw.available_for_purchase = 0 THEN 'not-for-sale'
        WHEN aw.inventory_quantity = 0     THEN 'sold'
        ELSE 'for-sale'
    END
"""

_ARTWORK_COLUMNS = f"""
    aw.id, aw.title, aw.year, aw.medium, aw.category, aw.description,
    aw.price_cents, aw.available_for_purchase, aw.inventory_quantity,
    aw.is_featured, aw.image, aw.image_width, aw.image_height,
    ar.name AS artist_name, ar.slug AS artist_slug,
    {_STATUS_CASE} AS status
"""

# The price menu sends values like "100000-300000" or "300000-": cents, low to
# high, an empty high meaning no ceiling. Keeping the allowed ranges in one
# dictionary means an unexpected value can simply be ignored.
PRICE_RANGES = {
    "0-100000": (0, 100000),
    "100000-300000": (100000, 300000),
    "300000-": (300000, None),
}


def get_artists():
    """All artists, fetched at most once per request.

    The homepage needs this list twice: once for its own artist sections, and
    once for the nav in base.html. Without the cache that is two identical
    queries for one page. `g` is per-request, so the cache cannot go stale
    between requests or leak between visitors.
    """
    if "artists" not in g:
        g.artists = query_db(
            "SELECT id, slug, name, lifespan, summary, bio, portrait"
            " FROM artists ORDER BY name"
        )
    return g.artists


def get_artist(slug):
    """Return the artist with this slug, or None if there is no such artist.

    The ? is a parameter placeholder. SQLite receives the query and the value
    separately, so the value is always treated as data and can never become
    part of the SQL.

    Writing this instead:

        f"SELECT ... WHERE slug = '{slug}'"

    would paste whatever a visitor typed in the address bar straight into the
    statement. A slug of  x' OR '1'='1  would then match every artist. That is
    SQL injection, and the ? is the entire defence against it.
    """
    return query_db(
        "SELECT id, slug, name, lifespan, summary, bio, portrait"
        " FROM artists WHERE slug = ?",
        (slug,),
        one=True,
    )


def get_featured_artworks():
    """Featured works, each with its artist's name attached.

    The JOIN replaces Stage 4's _with_artist_name: instead of looking up the
    artist for every artwork in Python, the database matches the two tables
    through the foreign key and returns the combined rows in one query.
    """
    return query_db(f"""
        SELECT {_ARTWORK_COLUMNS}
        FROM artworks aw
        JOIN artists ar ON ar.id = aw.artist_id
        WHERE aw.is_featured = 1
        ORDER BY aw.display_order, aw.id
    """)


def _like_pattern(text):
    """Wrap text in % wildcards for a LIKE search, escaping any it contains.

    In SQL, % matches anything and _ matches any single character. Without
    escaping, a visitor searching for % would match every work, and _ would
    quietly match more than they asked for. ! is declared as the escape
    character in the query below, so !% means a literal percent sign.
    """
    escaped = text.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return "%" + escaped + "%"


def search_artworks(q="", artist="", category="", status="", price=""):
    """Artworks matching the filters given. With no filters, all of them.

    The WHERE clause is assembled from the filters that are actually set.
    Note the split, because it is the whole safety story: the STRUCTURE of the
    query is built from strings we wrote ourselves, while every VALUE travels
    separately as a ? parameter. Nothing a visitor typed ever becomes SQL.
    """
    clauses = []
    params = []

    if q:
        clauses.append("""(
            aw.title LIKE ? ESCAPE '!' OR
            aw.medium LIKE ? ESCAPE '!' OR
            aw.category LIKE ? ESCAPE '!' OR
            ar.name LIKE ? ESCAPE '!'
        )""")
        params.extend([_like_pattern(q)] * 4)

    if artist:
        clauses.append("ar.slug = ?")
        params.append(artist)

    if category:
        clauses.append("aw.category = ?")
        params.append(category)

    if status:
        clauses.append(f"{_STATUS_CASE} = ?")
        params.append(status)

    # Anything not in the menu is ignored rather than trusted. This value came
    # from a query string, so it can be any text at all.
    if price in PRICE_RANGES:
        low, high = PRICE_RANGES[price]
        clauses.append("aw.price_cents >= ?")
        params.append(low)
        if high is not None:
            clauses.append("aw.price_cents < ?")
            params.append(high)

    # No filters set means no WHERE clause at all, and the query returns
    # everything, which is exactly what an unfiltered page wants.
    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    return query_db(f"""
        SELECT {_ARTWORK_COLUMNS}
        FROM artworks aw
        JOIN artists ar ON ar.id = aw.artist_id
        {where}
        ORDER BY aw.display_order, aw.id
    """, params)


def count_artworks():
    """How many works exist in total, for the "showing X of Y" line.

    COUNT(*) is answered by the database without sending any rows back.
    """
    return query_db("SELECT COUNT(*) AS total FROM artworks", one=True)["total"]


def get_categories():
    """The distinct categories actually in use, for the filter menu.

    DISTINCT collapses duplicate values, so three paintings produce one
    "Painting" option. Reading the options from the data means a new category
    appears in the filter the moment an artwork uses it — nothing to keep in
    sync by hand.
    """
    rows = query_db("SELECT DISTINCT category FROM artworks ORDER BY category")
    return [row["category"] for row in rows]


def get_artwork(artwork_id):
    """Return one artwork with its artist's name, or None if no such id exists.

    one=True is the difference between this and the list functions: it returns
    a single row instead of a list of them. Returning None for "not found" is
    deliberate — it is the caller, the route, that knows a missing artwork
    should become a 404 rather than an error.
    """
    return query_db(f"""
        SELECT {_ARTWORK_COLUMNS}
        FROM artworks aw
        JOIN artists ar ON ar.id = aw.artist_id
        WHERE aw.id = ?
    """, (artwork_id,), one=True)


def get_related_artworks(artist_slug, exclude_id, limit=3):
    """Other works by the same artist, for the foot of an artwork page.

    LIMIT caps how many rows come back. Combined with ORDER BY it means the
    database returns three rows, not all of them for Python to throw away.
    """
    return query_db(f"""
        SELECT {_ARTWORK_COLUMNS}
        FROM artworks aw
        JOIN artists ar ON ar.id = aw.artist_id
        WHERE ar.slug = ? AND aw.id != ?
        ORDER BY aw.display_order, aw.id
        LIMIT ?
    """, (artist_slug, exclude_id, limit))


def get_artworks_by_artist(slug):
    return query_db(f"""
        SELECT {_ARTWORK_COLUMNS}
        FROM artworks aw
        JOIN artists ar ON ar.id = aw.artist_id
        WHERE ar.slug = ?
        ORDER BY aw.display_order, aw.id
    """, (slug,))


# --- The cart ----------------------------------------------------------------
# The cart is a session value, not a table. Nothing here writes to the
# database, which is why Stage 11 needed no schema change at all.

CART_KEY = "cart"

# A ceiling on one line, whatever the inventory says. It stops a typo — or
# somebody editing the number field in dev tools — from putting 9,999 prints
# in a cart. The real limit is still the inventory; this is just a sane cap.
MAX_PER_LINE = 10


def get_cart():
    """The cart exactly as stored: {"4": 1, "2": 3}.

    The keys are STRINGS, not ints. A session is turned into JSON before it is
    signed, and JSON object keys are always strings: 4 goes in, "4" comes back.
    Everything that touches the cart uses str(id) for that reason.

    The isinstance check is for a cookie that is old, hand-edited or simply
    from a different version of this app. A cart we cannot understand is an
    empty cart, not a crash on every page.
    """
    cart = session.get(CART_KEY, {})
    return dict(cart) if isinstance(cart, dict) else {}


def save_cart(cart):
    """Write the cart back to the session.

    Note the assignment. Flask only re-signs and re-sends the cookie when it
    NOTICES the session changed, and it cannot notice a mutation inside a dict
    it handed you — cart["4"] = 1 on the object get_cart() returned may simply
    be lost. Read it out, change it, assign it back.

    Empty lines are dropped on the way out, so "remove" never has to be a
    special case anywhere else.
    """
    session[CART_KEY] = {key: qty for key, qty in cart.items() if qty > 0}


def cart_count():
    """Total items in the cart, for the number beside the nav link."""
    return sum(get_cart().values())


def get_artworks_by_ids(ids):
    """Fetch several artworks in one query rather than one query per id.

    The IN list needs one ? per id, so the STRUCTURE of the clause is built
    from a count we worked out ourselves, while every id still travels as a
    parameter. Same split as search_artworks: we write the SQL, the visitor
    only ever supplies values.
    """
    if not ids:
        return []

    placeholders = ", ".join("?" * len(ids))
    return query_db(f"""
        SELECT {_ARTWORK_COLUMNS}
        FROM artworks aw
        JOIN artists ar ON ar.id = aw.artist_id
        WHERE aw.id IN ({placeholders})
    """, ids)


def get_cart_lines():
    """The cart as real data: one line per work, priced from the database.

    Look at what the cookie actually contributes: an id and a quantity. The
    title, the price and the availability are read fresh here on every
    request. So a cart left open overnight shows this morning's truth, and a
    visitor who edited their own cookie can change what they are asking for
    but never what it costs.

    Each line carries an `issue`, re-derived now rather than trusted from when
    the work was added. Adding to a cart reserves nothing, so a work can go
    sold, or be withdrawn from sale, while it sits there. A line with an issue
    is shown but left out of the subtotal: we tell the visitor and let them
    decide, rather than silently changing what they asked for.
    """
    cart = get_cart()
    if not cart:
        return []

    ids = [int(key) for key in cart if key.isdigit()]
    by_id = {row["id"]: row for row in get_artworks_by_ids(ids)}

    lines = []

    # dicts keep insertion order, and the JSON round-trip through the cookie
    # preserves it, so the cart reads in the order things were added to it.
    for key, quantity in cart.items():
        artwork = by_id.get(int(key)) if key.isdigit() else None

        # The work no longer exists. There is nothing to show and nothing to
        # price, so the line just disappears.
        if artwork is None:
            continue

        if artwork["status"] == "sold":
            issue = "sold"
        elif artwork["status"] == "not-for-sale":
            issue = "not-for-sale"
        elif quantity > artwork["inventory_quantity"]:
            issue = "too-many"
        else:
            issue = None

        lines.append({
            "artwork": artwork,
            "quantity": quantity,
            "issue": issue,
            "subtotal_cents": artwork["price_cents"] * quantity,
        })

    return lines


def cart_subtotal(lines):
    """What the ready-to-buy lines come to.

    Lines with a problem are excluded, so the total never quotes a price for
    something the gallery cannot actually sell.
    """
    return sum(line["subtotal_cents"] for line in lines if line["issue"] is None)


def allowed_quantity(artwork):
    """The most of this work one visitor may put in a cart."""
    return min(artwork["inventory_quantity"], MAX_PER_LINE)


def add_to_cart(artwork, quantity):
    """The rules for adding a work, written once. Returns (outcome, message).

    outcome is one of:
        "added"        the full quantity went in
        "capped"       it went in, but was reduced to what is allowed
        "unavailable"  nothing went in: the work is sold or not for sale

    Two routes add to the cart -- the HTML form (/cart/add) and the API
    (/api/cart) -- and they differ only in how they ANSWER: one flashes a
    message and redirects, the other returns JSON. What is allowed must not
    differ, so it lives here and both call it. If the API had its own copy of
    these checks, the two would drift the first time either was edited.

    The message is shared too, so a visitor reads the same words whichever
    path their click took.
    """
    if artwork["status"] != "for-sale":
        return "unavailable", "That work is not available to buy."

    cart = get_cart()
    key = str(artwork["id"])
    allowed = allowed_quantity(artwork)
    wanted = cart.get(key, 0) + max(quantity, 1)

    if wanted > allowed:
        cart[key] = allowed
        outcome = "capped"
        message = (f"Only {allowed} of that work can be added. Your cart now "
                   f"holds {allowed}.")
    else:
        cart[key] = wanted
        outcome = "added"
        message = "Added to your cart."

    save_cart(cart)
    return outcome, message


# --- Remembered orders -------------------------------------------------------
# There are no accounts yet, so "your orders" can only mean the orders THIS
# BROWSER remembers. The session holds a list of references; the database holds
# everything true about them. Exactly the cart's shape: the cookie carries
# identifiers, never facts.
#
# The honest limitation is that a different device shows nothing, and clearing
# cookies loses the list. That is precisely what real accounts fix, at Stage 16.

ORDERS_KEY = "orders"

# A cookie is capped at about 4KB in total, shared with the cart, and every
# reference is 22 characters. Ten is generous and leaves plenty of room.
REMEMBERED_ORDERS = 10

# The statuses an order may have, and how each reads on a page. The database
# enforces the same list with a CHECK constraint (see schema.sql), so this
# dictionary and that constraint have to agree -- and the test suite checks
# that they do.
ORDER_STATUSES = {
    "pending": "Awaiting payment",
    "paid": "Paid",
    "shipped": "Shipped",
    "cancelled": "Cancelled",
}


def get_remembered_orders():
    """The references this browser has kept, newest first.

    Defensive about the contents for the same reason get_cart() is: this came
    out of a cookie, and a cookie can be old, hand-edited, or left over from a
    different version of the app. Anything unrecognisable is treated as no
    orders rather than allowed to raise on every page.
    """
    stored = session.get(ORDERS_KEY, [])
    if not isinstance(stored, list):
        return []
    return [ref for ref in stored if isinstance(ref, str)][:REMEMBERED_ORDERS]


def remember_order(reference):
    """Add an order to the front of this browser's list.

    Assigned back to the session rather than mutated in place, for the same
    reason the cart is: Flask re-sends the cookie only when it notices a
    change, and it cannot notice a list it handed you being appended to.
    """
    others = [ref for ref in get_remembered_orders() if ref != reference]
    session[ORDERS_KEY] = [reference] + others[:REMEMBERED_ORDERS - 1]


def get_orders_by_references(references):
    """Summaries of these orders, newest first.

    Two new pieces of SQL here:

    GROUP BY collapses many rows into one per group, and COUNT/SUM report on
    the rows that were collapsed. Without it, an order of three works would
    come back as three rows and the page would have to add them up in Python.

    LEFT JOIN keeps every row from the left-hand table even when the right has
    no match. A plain JOIN would silently drop an order that somehow had no
    lines -- and an order that exists but looks empty is exactly the kind of
    problem you want to SEE rather than have hidden by the query.

    COALESCE turns the NULL that SUM returns for no rows into 0, so the
    template never has to think about it.
    """
    if not references:
        return []

    placeholders = ", ".join("?" * len(references))
    return query_db(f"""
        SELECT o.id, o.reference, o.subtotal_cents, o.status, o.placed_at,
               COUNT(oi.id) AS line_count,
               COALESCE(SUM(oi.quantity), 0) AS work_count
          FROM orders o
          LEFT JOIN order_items oi ON oi.order_id = o.id
         WHERE o.reference IN ({placeholders})
         GROUP BY o.id
         ORDER BY o.placed_at DESC, o.id DESC
    """, references)


# --- Checkout ----------------------------------------------------------------

class OutOfStock(Exception):
    """Raised inside the checkout transaction when a work is no longer there.

    A custom exception type, rather than a returned flag, because it has to
    travel up out of the middle of a transaction and force a rollback. It
    carries the work it failed on, so the message can name it.
    """

    def __init__(self, artwork):
        super().__init__(f"{artwork['title']} is no longer available")
        self.artwork = artwork


class PaymentDeclined(Exception):
    """Raised when the mock payment step is told to decline."""


def validate_checkout(form):
    """Check the submitted details. Returns (values, errors).

    Both are returned, always. `values` is what the visitor typed, stripped of
    surrounding whitespace, so the form can be re-rendered with their work
    still in it. `errors` is empty when everything is fine.

    Validation happens HERE, on the server, whatever the browser did. The
    required= and type=email attributes in the form are a convenience for
    people using a browser; they are simply absent from a hand-written POST,
    and a check that can be skipped is not a check.
    """
    values = {
        "customer_name": form.get("customer_name", "").strip(),
        "customer_email": form.get("customer_email", "").strip(),
        "shipping_address": form.get("shipping_address", "").strip(),
    }
    errors = {}

    if not values["customer_name"]:
        errors["customer_name"] = "Please give a name for the order."
    elif len(values["customer_name"]) > 120:
        errors["customer_name"] = "That name is too long."

    email = values["customer_email"]
    if not email:
        errors["customer_email"] = "Please give an email address."
    elif email.count("@") != 1 or " " in email or not all(email.split("@")):
        # Deliberately loose. No regular expression correctly matches every
        # valid email address while rejecting every invalid one, and the ones
        # that try reject real addresses. The only true test of an address is
        # sending mail to it, which is Stage 14 business. This catches typing
        # into the wrong box, and stops there.
        errors["customer_email"] = "That does not look like an email address."

    if not values["shipping_address"]:
        errors["shipping_address"] = "Please give a delivery address."

    return values, errors


def place_order(lines, values, payment_approved):
    """Write the order and claim the stock, as one indivisible operation.

    This is the only function in the app that writes to the database, and the
    only one that manages a transaction. Everything between BEGIN and COMMIT
    either all happens or none of it does.

    Raises OutOfStock if a work was taken while the visitor was typing, or
    PaymentDeclined if the mock payment failed. Either way the ROLLBACK in the
    except block undoes every change made so far, so a failed checkout leaves
    the database exactly as it was.
    """
    db = get_db()

    # IMMEDIATE takes the write lock now, rather than at the first write. Two
    # checkouts for the last copy of one work therefore queue up here, and the
    # second runs its checks AFTER the first has committed, seeing the
    # decremented inventory rather than the stale one.
    db.execute("BEGIN IMMEDIATE")
    try:
        for line in lines:
            artwork = line["artwork"]

            # The check and the claim, in one statement.
            #
            # The WHERE decides whether it is allowed; the SET does it. No
            # other connection can act between them, because there is no
            # between: it is a single operation. The two-statement version --
            # SELECT the quantity, decide in Python, then UPDATE -- has a gap
            # in the middle, and two visitors buying the last copy of a work
            # both read "1 available" inside that gap.
            cursor = db.execute("""
                UPDATE artworks
                   SET inventory_quantity = inventory_quantity - ?
                 WHERE id = ?
                   AND available_for_purchase = 1
                   AND inventory_quantity >= ?
            """, (line["quantity"], artwork["id"], line["quantity"]))

            # rowcount is how many rows the UPDATE actually changed. 0 means
            # the WHERE matched nothing: someone else got there first.
            if cursor.rowcount != 1:
                raise OutOfStock(artwork)

        subtotal = cart_subtotal(lines)

        # The mock payment sits INSIDE the transaction, so a decline rolls the
        # inventory back with everything else. Stage 14 replaces this with
        # Stripe and will have to move it, because a real payment cannot be
        # undone by a ROLLBACK. That is a Stage 14 problem, and the simple
        # version is worth seeing first.
        if not payment_approved:
            raise PaymentDeclined()

        # token_urlsafe(16) is 16 random BYTES, not 16 characters: about
        # 3.4e38 possibilities. Guessing one is not a strategy.
        reference = secrets.token_urlsafe(16)

        cursor = db.execute("""
            INSERT INTO orders (reference, customer_name, customer_email,
                                shipping_address, subtotal_cents,
                                payment_method, status, placed_at)
            VALUES (?, ?, ?, ?, ?, 'mock', 'paid', ?)
        """, (reference, values["customer_name"], values["customer_email"],
              values["shipping_address"], subtotal,
              datetime.now(timezone.utc).isoformat(timespec="seconds")))

        order_id = cursor.lastrowid

        for line in lines:
            artwork = line["artwork"]

            # The snapshot. artwork_id records WHICH work was bought; these
            # columns record what it was called and what it cost at this
            # moment. Repricing a work next year must not rewrite a receipt
            # issued today.
            db.execute("""
                INSERT INTO order_items (order_id, artwork_id, title_at_purchase,
                                         artist_at_purchase, unit_price_cents,
                                         quantity)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (order_id, artwork["id"], artwork["title"],
                  artwork["artist_name"], artwork["price_cents"],
                  line["quantity"]))

        db.execute("COMMIT")

    except Exception:
        # Undo everything: the decremented inventory, the order row, the
        # lines. The database returns to exactly the state it was in before
        # BEGIN, and the exception then carries on up to the route.
        db.execute("ROLLBACK")
        raise

    return reference


def get_order(reference):
    """One order by its public reference, or None."""
    return query_db("""
        SELECT id, reference, customer_name, customer_email, shipping_address,
               subtotal_cents, payment_method, status, placed_at
          FROM orders WHERE reference = ?
    """, (reference,), one=True)


def get_order_items(order_id):
    """The lines of an order, read from the SNAPSHOT columns.

    Nothing here joins to artworks for a title or a price. Those columns are
    what the buyer was shown and charged, and they are the only honest source
    for a receipt. artwork_id is carried only for the link, so a reader can go
    and look at the work as it stands today.
    """
    return query_db("""
        SELECT oi.artwork_id, oi.title_at_purchase, oi.artist_at_purchase,
               oi.unit_price_cents, oi.quantity,
               oi.unit_price_cents * oi.quantity AS line_total_cents
          FROM order_items oi
         WHERE oi.order_id = ?
         ORDER BY oi.id
    """, (order_id,))


# --- Admin: who is logged in -------------------------------------------------
# Authentication answers "who are you?" -- the login. Authorisation answers
# "may you do this?" -- the lock on each admin page. There is one kind of user
# here, so authorisation is simply "is an admin logged in", but they remain
# two separate questions, and Stage 20 will care about the difference.

ADMIN_KEY = "admin_id"

# Length is what makes a password hard to guess, far more than rules about
# symbols and capitals, which mostly produce "Password1!". Twelve characters
# is a sensible floor; a passphrase of four ordinary words clears it easily.
MIN_PASSWORD_LENGTH = 12


def get_admin_by_username(username):
    """The admin row for this username, or None. Case-insensitive, because
    the column is declared COLLATE NOCASE in schema.sql."""
    return query_db(
        "SELECT id, username, password_hash FROM admins WHERE username = ?",
        (username,), one=True)


def current_admin():
    """The logged-in admin (id and username), or None. Looked up once per request.

    The session holds only the admin's id. The row is re-read from the
    database on every request rather than trusted from the cookie, for the
    same reason the cart re-reads prices: the cookie can say who you WERE.
    Deleting an admin's row therefore locks them out on their very next
    click, even though their cookie still carries the old id.
    """
    if "admin" not in g:
        admin = None
        admin_id = session.get(ADMIN_KEY)

        if isinstance(admin_id, int):
            admin = query_db("SELECT id, username FROM admins WHERE id = ?",
                             (admin_id,), one=True)
            if admin is None:
                # The account is gone. Forget it, so the stale id stops
                # being looked up on every request.
                session.pop(ADMIN_KEY, None)

        g.admin = admin
    return g.admin


def admin_required(view):
    """Lock a route so only a logged-in admin can reach it.

    This is a DECORATOR: a function that takes a function and returns a new
    one wrapped around it. Writing

        @admin_required
        def admin_dashboard(): ...

    is shorthand for  admin_dashboard = admin_required(admin_dashboard).
    From then on, calling the view really calls `wrapped` below, which checks
    first and only then hands over to the original.

    functools.wraps copies the original's name onto the wrapper. Flask uses a
    view's name as its endpoint -- what url_for("admin_dashboard") looks up --
    so without it, every locked route would be called "wrapped" and Flask
    would refuse to register the second one.
    """
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if current_admin() is None:
            # Remember where they were going, so logging in can take them
            # there. full_path keeps the query string, but ends in a bare "?"
            # when there is none, so fall back to the plain path then.
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("admin_login", next=target))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target):
    """Where to send someone after logging in: `target` if it is safely ours.

    `next` arrives in the URL, so it can say anything. Honouring it blindly is
    an OPEN REDIRECT: an attacker sends a link to the real login page with
    next=https://evil.example, the victim logs in on the genuine site, and is
    then handed to a fake one that asks them to "log in again".

    So only a path on this site is accepted: it must start with "/", carry no
    scheme or host, and not start with "//" -- which browsers read as "same
    scheme, different host". Backslashes are refused outright because some
    browsers treat /\\evil.example exactly like //evil.example. Anything else
    goes to the admin dashboard instead.
    """
    if target:
        parts = urlsplit(target)
        if (target.startswith("/") and not target.startswith("//")
                and "\\" not in target
                and not parts.scheme and not parts.netloc):
            return target
    return url_for("admin_dashboard")


@functools.cache
def _dummy_hash():
    """A real hash of nothing in particular, computed once and then reused.

    When someone logs in with a username that does not exist, there is no
    stored hash to check against -- and skipping the check would make that
    failure noticeably FASTER than a wrong password for a real admin. By
    timing the responses, an attacker could learn which usernames exist.
    Checking against this instead makes both failures take the same time.
    """
    return generate_password_hash(secrets.token_urlsafe(16))


def password_problem(password, username=""):
    """Why this password is not acceptable, or None if it is."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if username and password.lower() == username.lower():
        return "The password cannot be the username."
    return None


def set_admin_password(username, password):
    """Create this admin, or give an existing one a new password.

    generate_password_hash does everything a password needs: it adds a random
    SALT (so two admins with the same password get different hashes, and a
    precomputed table of common passwords is useless), and uses a method that
    is deliberately SLOW (a fraction of a second for one login; ruinous for
    anyone trying billions of guesses against a stolen database).

    Only the hash is written. The password itself exists in memory for the
    length of this call and nowhere else.
    """
    password_hash = generate_password_hash(password)
    db = get_db()

    if get_admin_by_username(username) is None:
        db.execute(
            "INSERT INTO admins (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
    else:
        db.execute("UPDATE admins SET password_hash = ? WHERE username = ?",
                   (password_hash, username))


# --- Template helpers --------------------------------------------------------

@app.template_filter("usd")
def usd(cents):
    """Turn 480000 into "$4,800". Money is stored as whole cents (an integer)
    because floats lose precision: 0.1 + 0.2 != 0.3 in binary arithmetic.
    Formatting is presentation, so it belongs here rather than in the data."""
    return "${:,.0f}".format(cents / 100)


@app.template_filter("placed")
def placed(iso_text):
    """Turn "2026-09-22T02:12:53+00:00" into "22 September 2026, 02:12 UTC".

    The database stores ISO 8601 because it is unambiguous and sorts correctly
    as text. That is the right thing to STORE and the wrong thing to show
    somebody. Same division as the usd filter: the data keeps the precise
    value, the filter decides how a human reads it.
    """
    moment = datetime.fromisoformat(iso_text)
    return moment.strftime("%d %B %Y, %H:%M UTC").lstrip("0")

@app.template_filter("order_status")
def order_status(value):
    """Turn "paid" into "Paid", and "pending" into "Awaiting payment".

    The database stores the short machine value, because that is what a CHECK
    constraint and a query want. How it reads to a person is presentation, so
    it belongs in a filter -- the same division as usd and placed.

    An unknown value is shown as-is rather than hidden. If a status ever
    reaches the page that this dictionary does not know about, seeing it is
    more useful than a blank space.
    """
    return ORDER_STATUSES.get(value, value)

@app.context_processor
def inject_site_globals():
    """Variables every template needs, whichever route rendered it.

    Flask calls this before rendering ANY template and merges the returned
    dict into that template's variables, so no route has to remember to pass
    the nav data.
    """
    return {
        "gallery_name": GALLERY_NAME,
        "nav_artists": get_artists(),

        # The nav shows this on every page, so it belongs here rather than in
        # each route. It reads the cookie only — no database query.
        "cart_count": cart_count(),

        # The cap is a gallery rule, and a rule belongs in one place. The
        # quantity inputs use it for their max= so the browser enforces the
        # same limit the server does.
        "max_per_line": MAX_PER_LINE,

        # The Orders link is hidden until this browser has placed one. An
        # empty page nobody can fill is worse than no link.
        "remembered_orders": len(get_remembered_orders()),

        # The admin bar in base.html shows only when someone is logged in.
        # The public site never links to /admin at all: there is no reason
        # to advertise a login page to everyone who visits.
        "current_admin": current_admin(),
    }


# --- Routes ------------------------------------------------------------------

@app.route("/")
def home():
    # Already sorted by the database, so the first row is the work the
    # gallery chose to lead with. Nothing here re-sorts or re-filters.
    featured = get_featured_artworks()

    # Guard against an empty result: featured[0] on [] would raise IndexError
    # and turn the whole homepage into a 500 error.
    spotlight = featured[0] if featured else None

    return render_template(
        "index.html",
        artists=get_artists(),
        spotlight=spotlight,
        featured=featured[1:],
    )


# <slug> is a URL parameter: it matches any single path segment and Flask
# passes it to the function as the `slug` argument. One route, every artist.
@app.route("/artists/<slug>")
def artist_page(slug):
    artist = get_artist(slug)

    # The slug comes from the address bar, so it can be anything a visitor
    # types. An unknown slug is the visitor's mistake, not a server crash.
    if artist is None:
        abort(404)

    return render_template(
        "artist.html",
        artist=artist,
        artworks=get_artworks_by_artist(slug),
    )


def filters_from(args):
    """Read the collection filters out of a query string.

    request.args is the query string: /gallery?artist=artist-two&q=oil
    .get() with a default turns a missing parameter into an empty filter, so a
    bare URL and a cleared form take the same path.

    Used by the All works page AND by /api/artworks, so both understand
    exactly the same filters. search_artworks() then validates the values.
    """
    return {
        "q": args.get("q", "").strip(),
        "artist": args.get("artist", ""),
        "category": args.get("category", ""),
        "status": args.get("status", ""),
        "price": args.get("price", ""),
    }


@app.route("/gallery")
def gallery():
    filters = filters_from(request.args)

    # The database returns only the matching rows, so the page is as small as
    # the result. The filters go back to the template as well, so the form can
    # show what is currently applied.
    return render_template(
        "gallery.html",
        artworks=search_artworks(**filters),
        categories=get_categories(),
        filters=filters,
        total=count_artworks(),
    )


# <int:artwork_id> only matches digits, and hands the function a real int.
# With a plain <artwork_id>, /artwork/abc would reach this function and rely
# on the query finding nothing; the converter refuses it at the routing table
# instead, before any of our code runs.
@app.route("/artwork/<int:artwork_id>")
def artwork_page(artwork_id):
    artwork = get_artwork(artwork_id)

    if artwork is None:
        abort(404)

    return render_template(
        "artwork.html",
        artwork=artwork,
        related=get_related_artworks(artwork["artist_slug"], artwork_id),
    )


# --- Cart routes -------------------------------------------------------------
# Every route that CHANGES the cart is a POST, and every one of them ends in a
# redirect rather than a rendered page. That pattern has a name,
# POST/Redirect/GET, and it exists because of what a browser does on reload:
# reloading a page that came from a POST re-sends the POST. Redirecting means
# the page the visitor ends up on was fetched with a plain GET, so refreshing
# it just asks for the cart again instead of adding the painting a second time.

@app.get("/cart")
def cart():
    lines = get_cart_lines()
    return render_template("cart.html", lines=lines, subtotal=cart_subtotal(lines))


@app.post("/cart/add")
def cart_add():
    """Put a work in the cart.

    request.form is the POST body, the counterpart to request.args. type=int
    asks Werkzeug to convert the value and hand back the default if it cannot,
    so "abc" in the quantity field becomes 1 rather than a 500 error.
    """
    artwork_id = request.form.get("artwork_id", type=int)
    quantity = request.form.get("quantity", default=1, type=int)

    # The id came from a form, so it can be anything. An id for a work that
    # does not exist is a request for a page that does not exist.
    artwork = get_artwork(artwork_id) if artwork_id is not None else None
    if artwork is None:
        abort(404)

    # The rules -- including refusing a work that is not for sale, which the
    # server must check even though the button is only shown for works that
    # are -- live in add_to_cart(). This route only decides how to answer.
    outcome, message = add_to_cart(artwork, quantity)

    if outcome == "unavailable":
        flash(message, "error")
        return redirect(url_for("artwork_page", artwork_id=artwork["id"]))

    flash(message, "notice" if outcome == "capped" else "success")
    return redirect(url_for("cart"))


@app.post("/cart/update")
def cart_update():
    """Change the quantity on one line. Zero or less means remove it."""
    artwork_id = request.form.get("artwork_id", type=int)
    quantity = request.form.get("quantity", default=0, type=int)

    cart = get_cart()
    key = str(artwork_id)
    artwork = get_artwork(artwork_id) if artwork_id is not None else None

    if artwork is None or quantity <= 0:
        # An unknown id and a quantity of zero both mean the same thing: the
        # line should not be there. Nothing to complain about either way.
        cart.pop(key, None)
    else:
        allowed = allowed_quantity(artwork)
        if quantity > allowed:
            quantity = allowed
            flash(f"Only {allowed} of that work are available.", "notice")
        cart[key] = quantity

    save_cart(cart)
    return redirect(url_for("cart"))


@app.post("/cart/remove")
def cart_remove():
    """Take one work out of the cart entirely."""
    cart = get_cart()

    # str(None) is "None", which is not a key in the cart, so a missing or
    # non-numeric id removes nothing rather than raising.
    cart.pop(str(request.form.get("artwork_id", type=int)), None)
    save_cart(cart)

    flash("Removed from your cart.", "notice")
    return redirect(url_for("cart"))


# --- Checkout routes ---------------------------------------------------------

def _checkout_blocker(lines):
    """Why this cart cannot be checked out, or None if it can.

    Called by both checkout routes. The GET needs it to decide whether to show
    the form at all; the POST needs it because nothing stops someone posting
    to /checkout without ever loading the page. Written once so the two can
    never disagree.
    """
    if not lines:
        return "Your cart is empty."
    if any(line["issue"] for line in lines):
        return "Some works in your cart are unavailable. Please review it first."
    return None


@app.get("/checkout")
def checkout():
    lines = get_cart_lines()

    blocker = _checkout_blocker(lines)
    if blocker:
        flash(blocker, "notice")
        return redirect(url_for("cart"))

    return render_template(
        "checkout.html",
        lines=lines,
        subtotal=cart_subtotal(lines),
        values={"customer_name": "", "customer_email": "", "shipping_address": ""},
        errors={},
    )


@app.post("/checkout")
def checkout_submit():
    """Validate, take the mock payment, and place the order.

    Note the two different endings. A REJECTED form re-renders in place, with
    the errors and everything already typed: redirecting would throw that
    typing away. A SUCCESSFUL order redirects, so a reload cannot place a
    second one. Redirect on success, re-render on failure.
    """
    lines = get_cart_lines()

    blocker = _checkout_blocker(lines)
    if blocker:
        flash(blocker, "notice")
        return redirect(url_for("cart"))

    values, errors = validate_checkout(request.form)

    if errors:
        # 400, not 200. The request was bad, and the status code says so --
        # the same conviction as returning 404 rather than a 200 page that
        # says "not found".
        return render_template(
            "checkout.html",
            lines=lines,
            subtotal=cart_subtotal(lines),
            values=values,
            errors=errors,
        ), 400

    # The MOCK payment. A dropdown on the form decides the outcome, because
    # there is no payment provider to ask yet and a failure path that cannot
    # be tested is a failure path that does not work. Stage 14 replaces this
    # with a real Stripe call.
    payment_approved = request.form.get("mock_payment") != "decline"

    try:
        reference = place_order(lines, values, payment_approved)
    except OutOfStock as gone:
        # Somebody bought it while this visitor was typing. The transaction
        # rolled back, so nothing was sold and no stock was taken.
        flash(f"{gone.artwork['title']} by {gone.artwork['artist_name']} sold "
              f"while you were checking out. Your cart has not been charged.",
              "error")
        return redirect(url_for("cart"))
    except PaymentDeclined:
        flash("The mock payment was declined. Nothing has been charged and "
              "your cart is unchanged.", "error")
        return redirect(url_for("checkout"))

    # The order exists, so the cart has done its job.
    session.pop(CART_KEY, None)

    # ...and this browser keeps the reference, so /orders can find it again
    # after the confirmation page is closed.
    remember_order(reference)

    return redirect(url_for("order_page", reference=reference))


@app.get("/orders")
def orders():
    """The orders this browser remembers.

    `missing` is the difference between what the session claims and what the
    database actually has. It is not a hypothetical: rebuilding the database
    with init_db.py --reset leaves the cookie pointing at orders that no
    longer exist, and saying so is much better than showing a short list with
    no explanation.
    """
    references = get_remembered_orders()
    found = get_orders_by_references(references)

    return render_template("orders.html", orders=found,
                           missing=len(references) - len(found))


@app.get("/order/<reference>")
def order_page(reference):
    """The confirmation page, found by the random reference rather than by id.

    There is no login yet, so this URL is the only thing protecting the name,
    email and address on it. That is why the reference is random: /order/3
    would invite anyone to try /order/2.
    """
    order = get_order(reference)

    if order is None:
        abort(404)

    return render_template("order.html", order=order,
                           items=get_order_items(order["id"]))


# --- JSON API ----------------------------------------------------------------
# The same data as the pages, as data rather than HTML, for any program that
# wants it: this site's own JavaScript today, anything else later.
#
# Returning a dict from a Flask view sends it as JSON, with the
# Content-Type: application/json header set for you.

def artwork_json(artwork):
    """One artwork in its PUBLIC shape.

    Built field by field on purpose, rather than turning the whole row into a
    dict. An API is a contract: the moment someone's code reads `price_cents`,
    renaming or removing it breaks them. So nothing appears here by accident
    -- not display_order, not is_featured, not whatever column gets added
    next year -- only what we have decided to promise.

    The business rules apply here exactly as they do on the page. The page
    hides the price of a work that is not for sale, so the API does too: a
    rule enforced in the HTML but leaked by the JSON was never enforced.

    _external=True makes the URLs absolute (http://host/artwork/1). A program
    reading this JSON has no page to be relative TO.
    """
    for_sale = artwork["status"] == "for-sale"

    return {
        "id": artwork["id"],
        "title": artwork["title"],
        "artist": {
            "name": artwork["artist_name"],
            "slug": artwork["artist_slug"],
            "url": url_for("artist_page", slug=artwork["artist_slug"], _external=True),
        },
        "year": artwork["year"],
        "medium": artwork["medium"],
        "category": artwork["category"],
        "description": artwork["description"],
        "status": artwork["status"],

        # null (Python's None) when the work cannot be bought, exactly as the
        # page shows no price then. Whole cents, as stored: formatting money
        # is the reader's job, and "$4,800" is useless to a program.
        "price_cents": artwork["price_cents"] if for_sale else None,
        "available_quantity": artwork["inventory_quantity"] if for_sale else 0,

        "image": {
            "url": url_for("static", filename="images/" + artwork["image"], _external=True),
            "width": artwork["image_width"],
            "height": artwork["image_height"],
        },
        "url": url_for("artwork_page", artwork_id=artwork["id"], _external=True),
    }


def api_error(status, message):
    """An error, as JSON, with a status code that matches it.

    A person reads a page; a program reads the number. So the number has to
    be right, and the body has to be JSON too -- a program expecting JSON
    that gets the HTML 404 page back has nothing it can parse.
    """
    return {"error": message}, status


@app.get("/api/artworks")
def api_artworks():
    """The collection, taking the same filters as the All works page.

    /api/artworks?status=for-sale&artist=artist-two

    One call to search_artworks(), the same function /gallery uses: the query,
    the validation of the filters and the ordering are all shared. This route
    only chooses the format.
    """
    rows = search_artworks(**filters_from(request.args))
    return {
        "count": len(rows),
        "artworks": [artwork_json(row) for row in rows],
    }


@app.get("/api/artworks/<int:artwork_id>")
def api_artwork(artwork_id):
    artwork = get_artwork(artwork_id)
    if artwork is None:
        return api_error(404, "No artwork with that id.")
    return artwork_json(artwork)


@app.post("/api/cart")
def api_cart_add():
    """Add a work to this visitor's cart, answering in JSON.

    Expects a JSON body:  {"artwork_id": 2, "quantity": 1}

    The cart is still the session cookie. fetch() sends cookies to its own
    site by default, so a call from the page's JavaScript finds the same cart
    the page itself shows.

    get_json(silent=True) returns None, rather than raising, when the body is
    not JSON or not labelled as JSON. Requiring the JSON label has a side
    benefit: an ordinary HTML form on another website cannot send it, so this
    endpoint is not reachable by the simplest cross-site trick. Cross-site
    request forgery in general is Stage 20.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error(400, 'Send a JSON object, e.g. {"artwork_id": 2}.')

    artwork_id = data.get("artwork_id")
    quantity = data.get("quantity", 1)

    # JSON has its own types, and "2" (a string) is not 2 (a number). Checked
    # rather than converted: an API that silently guesses what you meant hides
    # the caller's bug instead of reporting it.
    #
    # The bool check looks odd and is necessary. In Python, True is an int
    # (True == 1), so {"artwork_id": true} would pass isinstance(x, int) and
    # quietly mean artwork 1.
    for name, value in (("artwork_id", artwork_id), ("quantity", quantity)):
        if not isinstance(value, int) or isinstance(value, bool):
            return api_error(400, f"{name} must be a whole number.")

    artwork = get_artwork(artwork_id)
    if artwork is None:
        return api_error(404, "No artwork with that id.")

    outcome, message = add_to_cart(artwork, quantity)

    if outcome == "unavailable":
        # 409 Conflict: the request was well-formed, but the work's current
        # state -- sold, or not for sale -- will not allow it.
        return api_error(409, message)

    return {
        "outcome": outcome,
        "message": message,
        "quantity_in_cart": get_cart().get(str(artwork_id), 0),
        "cart_count": cart_count(),
        "cart_url": url_for("cart"),
    }


# --- Admin routes ------------------------------------------------------------

@app.get("/admin/login")
def admin_login():
    # Already logged in: nothing to do here, go where they were heading.
    if current_admin() is not None:
        return redirect(safe_next(request.args.get("next")))

    return render_template("admin/login.html",
                           next=request.args.get("next", ""),
                           username="", error=None)


@app.post("/admin/login")
def admin_login_submit():
    """Check a username and password, and log the admin in if they match.

    One message for every failure -- unknown username or wrong password --
    because telling them apart tells an attacker which usernames are real,
    which halves their work. See _dummy_hash() for the same idea applied to
    how long the answer takes.
    """
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")

    admin = get_admin_by_username(username) if username else None

    # check_password_hash hashes what was typed the same way, with the same
    # salt, and compares. It also compares in constant time, so how long the
    # comparison takes does not reveal how many characters were right.
    stored = admin["password_hash"] if admin is not None else _dummy_hash()
    if not (check_password_hash(stored, password) and admin is not None):
        # 400, like any rejected form. The username is sent back so it does
        # not have to be retyped; the password never is -- it should not
        # travel back to the browser inside a page.
        return render_template("admin/login.html", next=next_url,
                               username=username,
                               error="That username and password do not match."), 400

    session[ADMIN_KEY] = admin["id"]
    flash(f"Logged in as {admin['username']}.", "success")
    return redirect(safe_next(next_url))


@app.post("/admin/logout")
def admin_logout():
    """POST, not GET, and this is a case where it matters.

    A GET logout can be triggered by anything that makes the browser fetch a
    URL -- an <img src="/admin/logout"> on any page the admin visits would log
    them out. Harmless-sounding, but it is exactly the class of problem that
    becomes serious for every other admin action, so logout sets the pattern.

    Only the admin key is removed. The rest of the session -- a cart, the
    remembered orders -- belongs to the visitor, not to the admin login.
    """
    session.pop(ADMIN_KEY, None)
    flash("Logged out.", "notice")
    return redirect(url_for("home"))


# The ORDER of these two decorators matters. Decorators apply bottom-up, so
# @admin_required wraps the view first, and @app.get then registers the
# WRAPPED version. Swap them and Flask registers the original, unlocked view.
@app.get("/admin")
@admin_required
def admin_dashboard():
    """Every artwork, as the gallery sees it rather than as the public does.

    Same function as the All works page -- search_artworks() with no filters
    -- but a different audience, so different rules for what is shown: the
    admin sees the price of a work that is not for sale, the stock count, and
    whether it is featured, none of which the public pages display.
    """
    return render_template("admin/dashboard.html", artworks=search_artworks())


@app.after_request
def no_store_for_admin(response):
    """Tell the browser not to keep copies of admin pages.

    Without this, after logging out on a shared computer, the Back button can
    show the admin pages again straight from the browser's cache -- no request
    is made, so no login is checked. no-store means there is nothing to show.
    """
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/about")
def about():
    return "Placeholder gallery description."


@app.route("/health")
def health():
    return {"status": "ok", "stage": 16}


# --- Command line ------------------------------------------------------------

@app.cli.command("create-admin")
@click.argument("username")
def create_admin_command(username):
    """Create an admin, or change an existing admin's password.

        flask --app app create-admin yourname

    The password is asked for in the terminal with hide_input, so it is not
    shown as you type, not stored in your shell history (it was never part of
    the command), and not written anywhere except as a hash.

    `flask` runs this inside an application context, so get_db() works here
    exactly as it does in a request.
    """
    username = username.strip()
    if not username:
        raise click.BadParameter("the username cannot be blank")

    existing = get_admin_by_username(username)
    if existing is not None and not click.confirm(
            f"{existing['username']} already exists. Change their password?"):
        click.echo("Nothing changed.")
        return

    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    problem = password_problem(password, username)
    if problem:
        # ClickException prints the message and exits with a non-zero code,
        # without a traceback: a mistake, not a crash.
        raise click.ClickException(problem)

    set_admin_password(username, password)
    click.echo(f"{'Updated' if existing else 'Created'} admin {username!r}. "
               f"Log in at /admin/login.")


# --- Error handlers ----------------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    """Render our own 404 page instead of the plain Werkzeug one.

    Returning a tuple sets the status code explicitly. Returning just the
    template would send 200 OK with a page saying "not found", which lies to
    browsers, search engines and monitoring tools. The status code is part of
    the answer, not decoration.
    """
    if request.path.startswith("/api/"):
        return api_error(404, "Not found.")
    return render_template("404.html"), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """A real URL, asked for with the wrong method (GET /api/cart, say).

    Under /api/ the answer is JSON, like every other API response. The Allow
    header lists the methods that WOULD work, which is what the HTTP standard
    asks a 405 to include. Anywhere else, Flask's default page is fine:
    nobody reaches a 405 by clicking a link on this site.
    """
    if request.path.startswith("/api/"):
        body, status = api_error(405, "That method is not allowed here.")
        return body, status, {"Allow": ", ".join(sorted(error.valid_methods))}
    return error


if __name__ == "__main__":
    app.run(debug=True, port=5000)
