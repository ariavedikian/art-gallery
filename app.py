"""
Art Gallery — a Flask web application.

Stage 16: admin accounts, and a CMS for the collection and orders.

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
import hashlib
import io
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import click
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from PIL import Image, ImageOps
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

GALLERY_NAME = "Gallery Placeholder"

# The homepage's opening image. Kept here, beside the gallery's name, rather
# than written into index.html, so that at Stage 21 replacing it -- file, size
# and alt text -- is a change to data, and the template stays as it is.
HERO = {
    "image": "placeholders/hero.svg",
    "width": 1600,
    "height": 900,
    "alt": "Placeholder hero image",
}

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

# The largest request body Flask will accept, uploads included. Werkzeug checks
# the declared length BEFORE reading the body, so an oversized upload is
# refused with a 413 without ever being held in memory.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

# Built from database/schema.sql + seed.sql by: python init_db.py --reset
DATABASE_PATH = Path(__file__).resolve().parent / "database" / "art_gallery.db"

# The schema this code was written against: the PRAGMA user_version that
# schema.sql writes into the file. The two change together.
SCHEMA_VERSION = 1

# Database files already found to be the right version, so the check costs
# one statement per file per process rather than one per request.
_checked_databases = set()


def check_schema_version(db):
    """Refuse a database built from an older (or newer) schema.sql.

    The .db file is made from schema.sql ONCE. When schema.sql later gains a
    column, the file does not: the site then fails on whichever query first
    names the new column, with "no such column" and nothing about why. This
    turns that into one clear message at the first query, with the fix in it.
    """
    found = db.execute("PRAGMA user_version").fetchone()[0]
    if found != SCHEMA_VERSION:
        raise RuntimeError(
            f"The database at {DATABASE_PATH} was built from a different "
            f"schema.sql (version {found}; this code needs {SCHEMA_VERSION}). "
            f"Rebuild it with: python init_db.py --reset "
            f"(this empties the admins and orders tables)."
        )


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

        if DATABASE_PATH not in _checked_databases:
            check_schema_version(g.db)
            _checked_databases.add(DATABASE_PATH)

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

# An image's alt text: the one written for it, or, until someone writes one,
# "<title> by <artist>". Worked out here, once, so every <img> on the site
# and the lightbox (which copies it from the card) say the same thing.
_ALT_CASE = "COALESCE(aw.alt_text, aw.title || ' by ' || ar.name)"

_ARTWORK_COLUMNS = f"""
    aw.id, aw.title, aw.year, aw.medium, aw.category, aw.description,
    aw.price_cents, aw.available_for_purchase, aw.inventory_quantity,
    aw.is_featured, aw.image, aw.image_width, aw.image_height,
    ar.name AS artist_name, ar.slug AS artist_slug,
    {_STATUS_CASE} AS status,
    {_ALT_CASE} AS alt
"""

# The price menu sends values like "100000-300000" or "300000-": cents, low to
# high, an empty high meaning no ceiling. Keeping the allowed ranges in one
# dictionary means an unexpected value can simply be ignored.
PRICE_RANGES = {
    "0-100000": (0, 100000),
    "100000-300000": (100000, 300000),
    "300000-": (300000, None),
}

# The longest search that is run. Far longer than any title, and far below
# the 50,000-byte limit SQLite puts on a LIKE pattern (see filters_from).
MAX_SEARCH_LENGTH = 100


# One column list for both artist queries, with the portrait's alt text
# derived the same way as an artwork's.
_ARTIST_COLUMNS = """
    id, slug, name, lifespan, summary, bio, portrait,
    COALESCE(portrait_alt, 'Portrait of ' || name) AS portrait_alt
"""


def get_artists():
    """All artists, fetched at most once per request.

    The homepage needs this list twice: once for its own artist sections, and
    once for the nav in base.html. Without the cache that is two identical
    queries for one page. `g` is per-request, so the cache cannot go stale
    between requests or leak between visitors.
    """
    if "artists" not in g:
        g.artists = query_db(f"SELECT {_ARTIST_COLUMNS} FROM artists ORDER BY name")
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
        f"SELECT {_ARTIST_COLUMNS} FROM artists WHERE slug = ?",
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

    ids = [int(key) for key in cart if is_digits(key)]
    by_id = {row["id"]: row for row in get_artworks_by_ids(ids)}

    lines = []

    # dicts keep insertion order, and the JSON round-trip through the cookie
    # preserves it, so the cart reads in the order things were added to it.
    for key, quantity in cart.items():
        artwork = by_id.get(int(key)) if is_digits(key) else None

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


# The summary columns for a list of orders, shared by the visitor's list and
# the admin's. customer_name is included for the admin; the visitor's page
# simply does not show it.
_ORDER_SUMMARY_SELECT = """
    SELECT o.id, o.reference, o.customer_name, o.subtotal_cents, o.status,
           o.placed_at,
           COUNT(oi.id) AS line_count,
           COALESCE(SUM(oi.quantity), 0) AS work_count
      FROM orders o
      LEFT JOIN order_items oi ON oi.order_id = o.id
"""

# Which status may become which. Stage 13 deliberately left this unwritten
# until something could change a status; the admin is the first thing that
# can. Stage 14 adds pending -> paid and pending -> cancelled for the webhook.
ORDER_TRANSITIONS = {
    "paid": {"shipped"},
}


def change_order_status(reference, new_status):
    """Move an order to new_status, if the rules allow it from where it is now.

    The rule is enforced INSIDE the UPDATE, as a WHERE clause, not by reading
    the status first and deciding in Python. Same reason as the inventory
    claim: read-then-write leaves a gap, and a double-click on "Mark shipped"
    fits inside it. Here, the second click finds the order no longer 'paid',
    changes zero rows, and returns False.
    """
    allowed_from = sorted(old for old, targets in ORDER_TRANSITIONS.items()
                          if new_status in targets)
    if not allowed_from:
        raise ValueError(f"no status may become {new_status!r}")

    placeholders = ", ".join("?" * len(allowed_from))
    cursor = get_db().execute(f"""
        UPDATE orders SET status = ?
         WHERE reference = ? AND status IN ({placeholders})
    """, (new_status, reference, *allowed_from))
    return cursor.rowcount == 1


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
        {_ORDER_SUMMARY_SELECT}
         WHERE o.reference IN ({placeholders})
         GROUP BY o.id
         ORDER BY o.placed_at DESC, o.id DESC
    """, references)


def get_all_orders():
    """Every order, newest first, for the admin. Same summary columns as the
    visitor's own list -- one SELECT, two audiences."""
    return query_db(f"""
        {_ORDER_SUMMARY_SELECT}
         GROUP BY o.id
         ORDER BY o.placed_at DESC, o.id DESC
    """)


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


# The longest each checkout field may be. Without a limit, whatever a POST
# carries is stored and shown back on every visit to the order page -- up to
# Werkzeug's own ceiling of 500KB a field. 254 is the longest address email
# can actually deliver to (RFC 5321); the others are generous for real use.
CHECKOUT_LIMITS = {"customer_name": 120, "customer_email": 254,
                   "shipping_address": 500}


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

    # Last, so a length problem replaces any other message for that field:
    # a 300-character "email" is too long before it is anything else.
    for name, limit in CHECKOUT_LIMITS.items():
        if len(values[name]) > limit:
            errors[name] = f"Keep this under {limit} characters."

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

# The longest username an admin may have. create-admin refuses longer, so at
# login a longer one cannot belong to anybody and is never looked up. There is
# no MAXIMUM password length on purpose: a long passphrase is a good one, and
# the hash reduces any length to a fixed size before the slow part begins.
MAX_USERNAME_LENGTH = 64


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


# --- Admin: editing the collection -------------------------------------------

PLACEHOLDER_DIR = Path(app.static_folder) / "images" / "placeholders"

# Placeholders are SVG, and only SVG: files we drew ourselves and committed,
# so we can trust what is inside them. Uploaded images (Stage 17 part 2) are a
# different matter -- a stranger's file -- and will never be SVG, because an
# SVG can carry a <script> that would run as this site.
PLACEHOLDER_SUFFIXES = {".svg"}

# Uploaded images live here, under names we generate. They are content, not
# code -- like the database, they are gitignored -- and the database stores
# their path as "artworks/<name>", relative to static/images/ like any other.
UPLOAD_DIR = Path(app.static_folder) / "images" / "artworks"

# The formats an upload may be, as Pillow names them, and the extension each
# is saved with. The extension comes from what the file turned out to BE,
# never from the name it arrived with.
UPLOAD_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

# Every upload is also saved as smaller copies ("renditions") at these widths,
# so a phone showing a 300-pixel card is not sent a 4000-pixel photograph.
# Only widths SMALLER than the original are made: enlarging adds bytes, not
# detail. Roughly: a grid card on a phone or a retina laptop (480, 960), the
# artwork page (1600), the lightbox on a large screen (2400).
RENDITION_WIDTHS = (480, 960, 1600, 2400)

# Renditions are WebP whatever the original was: typically a quarter to a
# third smaller than a JPEG of the same visible quality, with transparency
# when a PNG needs it, and read by every current browser. Quality is not a
# percentage of anything -- it is the encoder's own scale -- and 82 is where
# the difference from the original stops being visible at display size.
RENDITION_QUALITY = 82

# What a file this site wrote looks like: 32 hex characters, an optional
# rendition width, one of our extensions. The sweep only ever deletes files
# that match, so a file someone put in the folder by hand is left alone.
_UPLOAD_NAME = re.compile(r"([0-9a-f]{32})(-\d+)?\.(jpg|png|webp)")

# The sweep leaves files younger than this. A save writes its file first and
# its row a moment later; a file caught in that moment has no row YET, and
# deleting it would leave the row about to be saved pointing at nothing.
SWEEP_MIN_AGE_SECONDS = 60 * 60

# The largest side an image may claim, in pixels. A sanity bound, not a
# design limit: anything bigger is a mistake or a hostile file.
MAX_IMAGE_SIDE = 20000

# The most pixels an upload may decode to. A compressed file can be tiny and
# still expand enormously: a PNG of 30,000 x 30,000 white pixels is a few
# hundred kilobytes on disk and several gigabytes in memory once decoded (a
# "decompression bomb"). The pixel count is in the file's header, so it can
# be checked before decoding. Pillow has its own guard at about 89 million
# pixels, left at its default: ours fires first, and Pillow's stays behind it
# as a second line (and logs a warning if anything ever gets that far).
MAX_IMAGE_PIXELS = 50_000_000

_SVG_TAG = "{http://www.w3.org/2000/svg}svg"

# The longest each text field may be. Not a database rule -- SQLite would store
# a novel in a TEXT column -- but a sanity check on what reaches the page.
TEXT_LIMITS = {"title": 200, "year": 40, "medium": 120, "category": 60,
               "description": 4000, "alt_text": 300}

# Digits, optionally followed by a point and one or two more digits. Checked
# BEFORE converting, so "1e5", "12.345" and "-5" are refused rather than
# quietly turned into something the admin did not mean.
#
# [0-9], not \d. In Python, \d means any Unicode digit, so it matches the
# Arabic-Indic "٣" and dozens of others, and Decimal would happily read them.
# A price is typed on a keyboard in ASCII; anything else is refused.
_PRICE_PATTERN = re.compile(r"[0-9]+(\.[0-9]{1,2})?")

# The same rule for whole numbers. str.isdigit() is NOT this test: it is true
# for "²" (superscript two), which int() then refuses with a crash, and for
# "٣", which int() quietly reads as 3. A number from a form is 0-9 or nothing.
_DIGITS = re.compile(r"[0-9]+")


def is_digits(text):
    """True if text is one or more ASCII digits, and nothing else."""
    return _DIGITS.fullmatch(text) is not None

# The columns the CMS writes, in one list shared by INSERT and UPDATE so the
# two can never disagree. These are names WE wrote, so building the SQL from
# them is structure, not user input -- the values still travel as ? params.
_ARTWORK_WRITE_COLUMNS = (
    "artist_id", "title", "year", "medium", "category", "description",
    "price_cents", "available_for_purchase", "inventory_quantity",
    "is_featured", "image", "image_width", "image_height", "display_order",
    "alt_text",
)


def _svg_length(text):
    """"900" or "900px" -> 900.0. Anything else ("100%", "12cm") -> None.

    A percentage is relative to wherever the SVG is placed, so it is not a
    size at all; physical units would need a DPI we do not have. Either way
    the caller falls back to the viewBox.
    """
    text = (text or "").strip().removesuffix("px")
    try:
        return float(text)
    except ValueError:
        return None


def image_size(path):
    """(width, height) in pixels, read from the image file itself -- or None.

    The admin used to type these, which meant they could be wrong. The file
    already knows its own size, so ask the file.

    Only ever called on files we chose from a known folder, or wrote
    ourselves. It opens whatever path it is given, so the path must be
    checked BEFORE it gets here.
    """
    if Path(path).suffix.lower() == ".svg":
        return _svg_size(path)

    # A JPEG, PNG or WebP states its size in its first few bytes. Image.open
    # reads only that header; the pixels are not decoded unless asked for.
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, SyntaxError, ValueError):
        return None


def _svg_size(path):
    """An SVG states its size in the attributes of its root <svg> element:
    width="900" height="1100", or failing that, a viewBox="0 0 900 1100"
    whose last two numbers are the drawing's width and height."""
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    if root.tag != _SVG_TAG:
        return None

    width = _svg_length(root.get("width"))
    height = _svg_length(root.get("height"))
    if width is None or height is None:
        box = (root.get("viewBox") or "").replace(",", " ").split()
        try:
            width, height = float(box[2]), float(box[3])
        except (IndexError, ValueError):
            return None

    size = round(width), round(height)
    if not all(1 <= side <= MAX_IMAGE_SIDE for side in size):
        return None
    return size


def image_choices(current=None):
    """The images the form may offer, each with its size: {path: (w, h)}.

    The placeholders, read from their folder so a new one appears without
    touching code -- plus, when editing, the work's CURRENT image, so it can
    be kept. `current` comes from the database, never from the form: other
    works' uploads are not on offer, so one form cannot point at another
    work's file.

    The size is None for a file whose size cannot be read; the form shows
    that rather than hiding it. One dict answers both questions the form
    asks -- "is this a file we offer?" and "how big is it?" -- so the two
    answers can never disagree.
    """
    choices = {f"placeholders/{path.name}": image_size(path)
               for path in sorted(PLACEHOLDER_DIR.iterdir())
               if path.suffix.lower() in PLACEHOLDER_SUFFIXES}
    if current and current not in choices:
        choices[current] = image_size(image_file(current))
    return choices


def image_file(stored):
    """Where the file for a stored image path lives on disk.

    "artworks/ab12.jpg" is an upload, in UPLOAD_DIR; anything else is under
    static/images/. The one place that knows this, so the code that writes
    uploads and the code that reads them can never look in different folders.
    """
    if is_upload(stored):
        return UPLOAD_DIR / stored.removeprefix("artworks/")
    return Path(app.static_folder) / "images" / stored


def is_upload(stored):
    """True for an uploaded image ("artworks/..."), false for a placeholder."""
    return stored.startswith("artworks/")


def rendition_widths(width):
    """The rendition widths made for an original this wide: only smaller ones."""
    return [w for w in RENDITION_WIDTHS if w < width]


def rendition_path(stored, width):
    """ "artworks/ab12.jpg", 960 -> "artworks/ab12-960.webp".

    Worked out from the original's name, never stored. The database keeps one
    fact -- the original and its width -- and which renditions exist follows
    from it and RENDITION_WIDTHS. Store facts, derive conclusions.
    """
    return f"artworks/{Path(stored).stem}-{width}.webp"


def make_renditions(image, colour_profile):
    """{width: WebP bytes} for each rendition of a decoded, upright image."""
    # A palette ("P") or one-bit image cannot be resized smoothly: Pillow
    # quietly falls back to picking the nearest pixel, and the result stays
    # limited to the old palette. Convert to full colour first. A greyscale
    # image's colour profile describes grey, so it cannot be attached to the
    # RGB copy; a palette's colours are already RGB, so its profile can.
    if image.mode not in ("RGB", "RGBA"):
        if image.mode not in ("P", "PA"):
            colour_profile = None
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")

    renditions = {}
    for width in rendition_widths(image.width):
        height = max(1, round(image.height * width / image.width))
        # LANCZOS: the slowest of Pillow's resampling filters, and the one
        # that keeps fine detail -- brushwork, hatching -- when shrinking.
        smaller = image.resize((width, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        smaller.save(buffer, "WEBP", quality=RENDITION_QUALITY,
                     icc_profile=colour_profile)
        renditions[width] = buffer.getvalue()
    return renditions


def prepare_upload(file):
    """Decode an uploaded file and re-encode a clean copy of it.

    Returns (upload, None) on success, where upload is
    {"data": bytes, "suffix": ".jpg", "size": (w, h),
     "renditions": {width: bytes}}; or (None, message).
    Writes nothing to disk: this is validation, and validation has no side
    effects. write_upload() does the writing, once the whole form is good.

    Nothing the browser says about the file is used. The filename, its
    extension and its Content-Type are all typed or chosen by the sender.
    The only way to know what a file IS is to decode it -- and the only safe
    thing to keep is a copy we encoded ourselves, from the decoded pixels.
    """
    try:
        # formats= limits which decoders Pillow will even try. Pillow reads
        # dozens of formats, some old and rarely exercised; a file cannot
        # reach a decoder we did not list.
        with Image.open(file.stream, formats=list(UPLOAD_FORMATS)) as image:
            width, height = image.size
            if max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
                return None, (f"This image is {width:,} \u00d7 {height:,} pixels, which "
                              f"is more than this site accepts. Resize it and try again.")

            # Now decode every pixel. A truncated or corrupt file fails HERE,
            # not later on a visitor's screen.
            image.load()

            # Phone cameras save "MPO", a JPEG with a second picture tucked
            # inside. Pillow opens it through the JPEG decoder but reports
            # its own name. It is a JPEG; we keep the first picture.
            kind = "JPEG" if image.format == "MPO" else image.format
            colour_profile = image.info.get("icc_profile")

            # A camera often saves the picture sideways and adds a note,
            # "rotate 90 degrees", in the EXIF metadata. We are about to
            # throw the metadata away, so turn the pixels upright first,
            # or portrait photographs would land on their side.
            clean = ImageOps.exif_transpose(image)
    except Image.DecompressionBombError:
        return None, "This image has too many pixels for this site. Resize it and try again."
    except (OSError, SyntaxError, ValueError):
        return None, ("This file is not a JPEG, PNG or WebP image, or it is damaged. "
                      "(iPhone HEIC photos need exporting as JPEG first.)")

    # JPEG holds only greyscale or RGB, as browsers expect it; a print-shop
    # CMYK JPEG is converted. Its colour profile described CMYK, so it goes.
    if kind == "JPEG" and clean.mode not in ("L", "RGB"):
        clean, colour_profile = clean.convert("RGB"), None
    if kind == "WEBP" and clean.mode not in ("RGB", "RGBA"):
        clean = clean.convert("RGBA")

    # Saved from pixels, with nothing carried over but the colour profile,
    # which is what makes the colours of a photographed painting render as
    # photographed. Everything else in the original is left behind: EXIF
    # (GPS position, camera serial number), text comments, and any bytes
    # hidden after the image data.
    options = {"JPEG": {"quality": 95}, "WEBP": {"quality": 95},
               "PNG": {"optimize": True}}[kind]
    buffer = io.BytesIO()
    clean.save(buffer, kind, icc_profile=colour_profile, **options)
    return {"data": buffer.getvalue(), "suffix": UPLOAD_FORMATS[kind],
            "size": clean.size,
            "renditions": make_renditions(clean, colour_profile)}, None


def write_upload(record):
    """If the form uploaded a file, save it and point the record at it.

    Writes the original and its renditions. Returns the list of paths written
    (empty when there was no upload); the caller keeps it so it can delete
    them again if the row is not written.

    The name is generated, never taken from the upload. A visitor's filename
    can hold "../", spaces, characters Windows refuses, names Windows reserves
    (CON, NUL), a name another file already has, or something private
    ("IMG_2031 client's flat.jpg"). Random hex avoids all of it; hex rather
    than mixed case because Windows treats "aB" and "Ab" as the same file.

    Mode "xb" means create, and refuse if the file already exists. A name is
    written once and never overwritten, so a path in the database always
    means the same bytes.
    """
    upload = record["upload"]
    if upload is None:
        return []
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = "artworks/" + secrets.token_hex(16) + upload["suffix"]
    files = {stored: upload["data"]}
    files.update({rendition_path(stored, width): data
                  for width, data in upload["renditions"].items()})

    # All or nothing. If the disk fills on the third file, the two already
    # written are removed before the error goes on up: a half-written set
    # would be an original missing some of the copies the page asks for.
    written = []
    try:
        for name, data in files.items():
            path = image_file(name)
            with open(path, "xb") as file:
                written.append(path)
                file.write(data)
    except BaseException:
        discard_upload(written)
        raise

    record["image"] = stored
    return written


def discard_upload(paths):
    """Delete files written for a row that was never saved."""
    for path in paths:
        path.unlink(missing_ok=True)


def image_files(stored):
    """Every file on disk that belongs to an uploaded image.

    The original, plus every "<name>-<width>.webp" beside it -- found by
    looking, not worked out from RENDITION_WIDTHS. If the widths change one
    day, renditions made at the old widths still belong to this image and
    still have to go when it does.
    """
    original = image_file(stored)
    return [original] + sorted(UPLOAD_DIR.glob(f"{original.stem}-*.webp"))


def remove_image_files(stored):
    """Delete an uploaded image's files, if no artwork uses it any more.

    Called only AFTER the database change that stopped using it has been
    saved: the mirror of creating, which writes the file before the row.
    Either way round, the worst a crash in between can leave is a stray
    file, never a row pointing at a missing one.

    The database decides whether the image is unused, not the caller: if any
    row still names it, nothing is deleted. Placeholders are never deleted.

    A file that will not delete (on Windows, one that is open elsewhere) is
    logged and left for `flask sweep-uploads`. The save it follows has
    already happened, and must not be reported as failed because tidying up
    afterwards did not work.
    """
    if not is_upload(stored):
        return
    if query_db("SELECT 1 FROM artworks WHERE image = ?", (stored,), one=True):
        return
    for path in image_files(stored):
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            app.logger.warning("Could not delete %s (%s); "
                               "flask sweep-uploads will retry.", path, error)


def parse_price(text):
    """"$4,800.50" -> 480050 cents, or None if it is not a price.

    Decimal, never float. float("4800.10") is stored in binary as something
    fractionally different from 4800.10, and multiplying by 100 can then land
    a cent off. Decimal does arithmetic in base ten, exactly as written.
    """
    cleaned = text.strip().replace("$", "").replace(",", "")
    if not _PRICE_PATTERN.fullmatch(cleaned):
        return None
    return int(Decimal(cleaned) * 100)


def price_for_input(cents):
    """480050 -> "4800.50", for putting a stored price back in the form.

    Integer division and remainder, so no float is involved on the way out
    either.
    """
    return f"{cents // 100}.{cents % 100:02d}"


def parse_whole_number(text, low, high):
    """The int in text if it is a whole number from low to high, else None."""
    text = text.strip()
    if not is_digits(text):
        return None
    number = int(text)
    return number if low <= number <= high else None


def get_artwork_for_edit(artwork_id):
    """One artwork's STORED columns, as the edit form needs them.

    Not get_artwork(): that returns the public shape -- artist name rather
    than artist_id, a derived status, no display_order. The form edits the
    stored facts, so it reads the stored facts.
    """
    return query_db(f"""
        SELECT id, {", ".join(_ARTWORK_WRITE_COLUMNS)}
          FROM artworks WHERE id = ?
    """, (artwork_id,), one=True)


def artwork_form_values(artwork=None):
    """What the form fields show: an existing work's values, or new defaults.

    Everything becomes a string, because that is what a form field holds and
    what comes back when it is submitted. Checkboxes are the exception: they
    are just ticked or not.
    """
    if artwork is None:
        return {"artist_id": "", "title": "", "year": "", "medium": "",
                "category": "", "description": "", "price": "",
                "inventory_quantity": "1", "available_for_purchase": True,
                "is_featured": False, "image": "", "display_order": "100",
                "alt_text": ""}

    return {
        "artist_id": str(artwork["artist_id"]),
        "title": artwork["title"],
        "year": artwork["year"] or "",
        "medium": artwork["medium"],
        "category": artwork["category"],
        "description": artwork["description"],
        "price": price_for_input(artwork["price_cents"]),
        "inventory_quantity": str(artwork["inventory_quantity"]),
        "available_for_purchase": bool(artwork["available_for_purchase"]),
        "is_featured": bool(artwork["is_featured"]),
        "image": artwork["image"],
        "display_order": str(artwork["display_order"]),
        "alt_text": artwork["alt_text"] or "",
    }


def validate_artwork(form, files, current_image=None):
    """Check a submitted artwork form. Returns (values, errors, record).

    values  what was typed, as strings, so a rejected form comes back intact
    errors  field name -> message; empty when all is well
    record  the converted values ready for the database, or None on errors.
            When a file was uploaded, record["upload"] holds the prepared
            copy and record["image"] is None until write_upload() names it.

    current_image is the work's image as the DATABASE has it, when editing.

    Same shape as validate_checkout: the server is the only validation that
    counts, and the admin form has novalidate on it for the same reason.
    """
    values = {name: form.get(name, "").strip() for name in (
        "artist_id", "title", "year", "medium", "category", "description",
        "price", "inventory_quantity", "image", "display_order", "alt_text")}

    # An UNTICKED checkbox sends nothing at all -- not "off", not "0", just an
    # absent name. So "ticked" can only mean "the name is present".
    values["available_for_purchase"] = "available_for_purchase" in form
    values["is_featured"] = "is_featured" in form

    errors = {}

    # Each value checked against a known set, or a pattern, or a range.
    # Nothing from the form is trusted because the menu only offered good
    # options: a POST can be written by hand with any value at all.
    artist_ids = {artist["id"] for artist in get_artists()}
    artist_id = int(values["artist_id"]) if is_digits(values["artist_id"]) else None
    if artist_id not in artist_ids:
        errors["artist_id"] = "Choose an artist."

    for name in ("title", "medium", "category", "description"):
        if not values[name]:
            errors[name] = "Required."
    for name, limit in TEXT_LIMITS.items():
        if len(values[name]) > limit:
            errors[name] = f"Keep this under {limit} characters."

    price_cents = parse_price(values["price"])
    if price_cents is None:
        errors["price"] = "A price in dollars, like 4800 or 4,800.50."

    inventory = parse_whole_number(values["inventory_quantity"], 0, 10000)
    if inventory is None:
        errors["inventory_quantity"] = "A whole number from 0 to 10,000."

    # An uploaded file wins over the menu. An empty file input still sends a
    # part, with filename "", so "was a file chosen?" means "is there a name".
    upload = None
    file = files.get("image_file")
    if file and file.filename:
        upload, problem = prepare_upload(file)
        if problem:
            errors["image_file"] = problem
        else:
            width, height = upload["size"]
    else:
        # The size is not asked for: it is read from the file. The allowlist
        # check comes first, and it has to -- image_size() opens whatever path
        # it is handed, and "../../app.py" is a path too. Only a name that is
        # a key in image_choices() ever reaches the filesystem. Any
        # image_width or image_height in the POST is simply never read.
        images = image_choices(current_image)
        if values["image"] not in images and is_upload(values["image"]):
            # An upload the form showed as this work's image, which is not
            # this work's image now: someone replaced it after the form
            # was opened, and its files may already be gone.
            errors["image"] = ("This work's image was changed while the form was "
                               "open. Check the image, then save again.")
        elif values["image"] not in images:
            errors["image"] = "Choose an image, or upload one."
        elif images[values["image"]] is None:
            errors["image"] = "This file's size cannot be read. Choose another image."
        else:
            width, height = images[values["image"]]

    display_order = parse_whole_number(values["display_order"], 0, 100000)
    if display_order is None:
        errors["display_order"] = "A whole number. Lower numbers hang first."

    if errors:
        # A browser will not let a page fill in a file input -- otherwise any
        # page could quietly upload a file of its choosing from your disk. So
        # a rejected form comes back with everything EXCEPT the file, and
        # says so rather than letting it vanish unexplained.
        if upload is not None:
            errors["image_file"] = ("Your image was fine, but nothing was saved "
                                    "because of the problems below. Choose the "
                                    "file again.")
        return values, errors, None

    record = {
        "artist_id": artist_id,
        "title": values["title"],
        # A blank year becomes NULL -- "unknown" -- rather than an empty
        # string, which would mean "deliberately blank". Schema.sql draws the
        # same distinction.
        "year": values["year"] or None,
        "medium": values["medium"],
        "category": values["category"],
        "description": values["description"],
        "price_cents": price_cents,
        "available_for_purchase": int(values["available_for_purchase"]),
        "inventory_quantity": inventory,
        "is_featured": int(values["is_featured"]),
        "image": None if upload else values["image"],
        "image_width": width,
        "image_height": height,
        "display_order": display_order,
        # Blank means "not written yet" -- NULL, so the site uses its
        # fallback -- rather than an empty alt="", which would tell a screen
        # reader the image is decoration and skip it entirely.
        "alt_text": values["alt_text"] or None,
        "upload": upload,
    }
    return values, {}, record


def insert_artwork(record):
    """Add a new artwork. Returns its id."""
    columns = ", ".join(_ARTWORK_WRITE_COLUMNS)
    placeholders = ", ".join("?" * len(_ARTWORK_WRITE_COLUMNS))
    cursor = get_db().execute(
        f"INSERT INTO artworks ({columns}) VALUES ({placeholders})",
        [record[column] for column in _ARTWORK_WRITE_COLUMNS])
    return cursor.lastrowid


def update_artwork(artwork_id, record, loaded_inventory, loaded_image):
    """Save an edited artwork -- unless its stock changed since the form loaded,
    or its image changed since this request read it.

    loaded_inventory is the stock the form showed when it was opened, carried
    through a hidden field. The UPDATE only matches if the stock is STILL that
    number. If a sale happened in between, it matches nothing and returns
    False, rather than writing the old number back over the sale.

    That is optimistic concurrency: assume nobody else will interfere, but
    check at the moment of writing. Only the stock is guarded, because it is
    the only column that anything other than the admin ever changes.

    The image is guarded for a different reason (Stage 17): replacing an
    image now DELETES the old one's files. If another save replaced it
    between this request reading the row and this UPDATE, writing the old
    name back would point the work at files that are already gone. So the
    UPDATE also requires the image to still be the one this request read.
    """
    assignments = ", ".join(f"{column} = ?" for column in _ARTWORK_WRITE_COLUMNS)
    cursor = get_db().execute(
        f"UPDATE artworks SET {assignments} "
        f"WHERE id = ? AND inventory_quantity = ? AND image = ?",
        [record[column] for column in _ARTWORK_WRITE_COLUMNS]
        + [artwork_id, loaded_inventory, loaded_image])
    return cursor.rowcount == 1


def count_sales(artwork_id):
    """How many order lines refer to this work. Above zero, it cannot be deleted."""
    return query_db("SELECT COUNT(*) AS n FROM order_items WHERE artwork_id = ?",
                    (artwork_id,), one=True)["n"]


# --- Template helpers --------------------------------------------------------

@app.template_filter("srcset")
def srcset(art):
    """The srcset attribute for a work's image, or "" if it has none.

    srcset lists the same picture at several widths ("...-480.webp 480w,
    ...-960.webp 960w, ...jpg 3000w"); the browser picks one, using `sizes`
    to know how wide it will be drawn and the screen's pixel density. The
    original goes last, at its own width, for a screen that wants more than
    the largest rendition. A placeholder is an SVG, which is sharp at any
    size, so it gets no srcset at all.
    """
    if not is_upload(art["image"]):
        return ""
    candidates = [(rendition_path(art["image"], width), width)
                  for width in rendition_widths(art["image_width"])]
    candidates.append((art["image"], art["image_width"]))
    return ", ".join(f"{url_for('static', filename='images/' + path)} {width}w"
                     for path, width in candidates)


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

        # The same idea for text: the maxlength= on a field is the server's
        # own limit, read from here, so the two cannot drift apart. The
        # browser's copy is a convenience; the server's is the check.
        "input_limits": {"q": MAX_SEARCH_LENGTH, "username": MAX_USERNAME_LENGTH,
                         **CHECKOUT_LIMITS},

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
        hero=HERO,
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

    The search text is cut to MAX_SEARCH_LENGTH. SQLite refuses a LIKE
    pattern over 50,000 bytes with an error, so without the cut anyone could
    turn this page into a 500 by making the URL long. Cut rather than
    refused, because the box shows the text back: the visitor sees exactly
    what was searched for.
    """
    return {
        "q": args.get("q", "").strip()[:MAX_SEARCH_LENGTH],
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

    # Too long to be anyone is treated exactly like "no such user": the dummy
    # hash below still runs, and the same message comes back. Only the cut
    # username is echoed into the page, never the whole of what was sent.
    if len(username) > MAX_USERNAME_LENGTH:
        username, admin = username[:MAX_USERNAME_LENGTH], None
    else:
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


def _artwork_form(template_values, errors, artwork=None, loaded_inventory=None,
                  status=200):
    """Render the artwork form, for creating or editing. One template, both jobs.

    `artwork` is the stored row when editing, so the form can show the
    current image and offer to keep it.
    """
    current_image = artwork["image"] if artwork else None
    return render_template(
        "admin/artwork_form.html",
        values=template_values, errors=errors,
        artwork_id=artwork["id"] if artwork else None,
        artwork=artwork, loaded_inventory=loaded_inventory,
        artists=get_artists(), categories=get_categories(),
        images=image_choices(current_image),
        accepted_types=", ".join(f"image/{kind.lower()}" for kind in UPLOAD_FORMATS),
        max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
    ), status


@app.get("/admin/artworks/new")
@admin_required
def admin_artwork_new():
    return _artwork_form(artwork_form_values(), {})


@app.post("/admin/artworks/new")
@admin_required
def admin_artwork_create():
    values, errors, record = validate_artwork(request.form, request.files)
    if errors:
        return _artwork_form(values, errors, status=400)

    # The file is written first, then the row that points at it. A file and a
    # database row cannot share a transaction, so if the row is not written
    # the file is deleted again -- compensation, not rollback, the same idea
    # as cancelling an order in Stage 14. This order means the worst case is
    # a stray file nobody sees, never a row pointing at a file that is not
    # there, which would be a broken image on the public site.
    written = write_upload(record)
    artwork_id = None
    try:
        artwork_id = insert_artwork(record)
    finally:
        if artwork_id is None:
            discard_upload(written)

    flash(f"Added \u201c{record['title']}\u201d (#{artwork_id}).", "success")
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/artworks/<int:artwork_id>/edit")
@admin_required
def admin_artwork_edit(artwork_id):
    artwork = get_artwork_for_edit(artwork_id)
    if artwork is None:
        abort(404)
    return _artwork_form(artwork_form_values(artwork), {}, artwork,
                         loaded_inventory=artwork["inventory_quantity"])


@app.post("/admin/artworks/<int:artwork_id>/edit")
@admin_required
def admin_artwork_update(artwork_id):
    artwork = get_artwork_for_edit(artwork_id)
    if artwork is None:
        abort(404)

    loaded = parse_whole_number(request.form.get("loaded_inventory", ""), 0, 10**9)
    values, errors, record = validate_artwork(request.form, request.files,
                                              current_image=artwork["image"])
    if errors or loaded is None:
        return _artwork_form(values, errors, artwork, loaded, status=400)

    # Same order as creating: file first, and the file survives only if the
    # UPDATE saved. A refused UPDATE (the 409 below) counts as not saved.
    written = write_upload(record)
    saved = False
    try:
        saved = update_artwork(artwork_id, record, loaded, artwork["image"])
    finally:
        if not saved:
            discard_upload(written)

    if not saved:
        # Something moved under the form: the stock (almost certainly a sale)
        # or the image (another save). Re-read what they are NOW, show them,
        # and let the admin decide. Everything else they typed is kept.
        current = get_artwork_for_edit(artwork_id)
        if current is None:
            abort(404)
        now = current["inventory_quantity"]
        errors = {}
        if now != loaded:
            values["inventory_quantity"] = str(now)
            errors["inventory_quantity"] = (
                f"Stock changed from {loaded} to {now} while you were editing "
                f"(probably a sale). Check this number, then save again.")
        if current["image"] != artwork["image"]:
            values["image"] = current["image"]
            errors["image"] = ("This work's image was changed by someone else "
                               "just now. Check the image, then save again.")
        if written:
            errors["image_file"] = "Nothing was saved, so choose the file again."
        # 409 Conflict: the request was fine; the work's state moved under it.
        return _artwork_form(values, errors, current, now, status=409)

    # Saved. If that replaced an upload, its files are now unused.
    if record["image"] != artwork["image"]:
        remove_image_files(artwork["image"])

    flash(f"Saved \u201c{record['title']}\u201d.", "success")
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/artworks/<int:artwork_id>/delete")
@admin_required
def admin_artwork_delete_confirm(artwork_id):
    """Ask before deleting. A page, not a JavaScript confirm(), so the
    question is still asked with JavaScript off."""
    artwork = get_artwork(artwork_id)
    if artwork is None:
        abort(404)
    return render_template("admin/artwork_delete.html", artwork=artwork,
                           sales=count_sales(artwork_id))


@app.post("/admin/artworks/<int:artwork_id>/delete")
@admin_required
def admin_artwork_delete(artwork_id):
    """Delete a work -- unless it has been sold.

    The confirmation page already warns when a work has sales. But that page
    is a courtesy; THIS is the rule, and the rule belongs to the database:
    order_items.artwork_id is ON DELETE RESTRICT, so SQLite itself refuses.
    We catch its refusal and explain it, rather than check first and hope
    nothing changed between the check and the DELETE.
    """
    artwork = get_artwork(artwork_id)
    if artwork is None:
        abort(404)

    # RETURNING hands back the image of the row actually deleted, in the same
    # statement -- not the one read a moment ago, which another save could
    # have replaced since. fetchall() also runs the statement to completion.
    try:
        deleted = get_db().execute(
            "DELETE FROM artworks WHERE id = ? RETURNING image",
            (artwork_id,)).fetchall()
    except sqlite3.IntegrityError:
        flash(f"\u201c{artwork['title']}\u201d has been sold, so it cannot be "
              "deleted: its orders still point at it. To take it off sale, "
              "untick \u201cOffered for sale\u201d instead.", "error")
        return redirect(url_for("admin_artwork_edit", artwork_id=artwork_id))

    # The row is gone; now its files. Row first, then files.
    for row in deleted:
        remove_image_files(row["image"])

    flash(f"Deleted \u201c{artwork['title']}\u201d (#{artwork_id}).", "notice")
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/orders")
@admin_required
def admin_orders():
    return render_template("admin/orders.html", orders=get_all_orders(),
                           transitions=ORDER_TRANSITIONS)


@app.post("/admin/orders/<reference>/ship")
@admin_required
def admin_order_ship(reference):
    if change_order_status(reference, "shipped"):
        flash(f"Order {reference} marked shipped.", "success")
        return redirect(url_for("admin_orders"))

    # Nothing changed. Either there is no such order, or it is not in a state
    # that may become shipped -- already shipped, say, from a double-click.
    order = get_order(reference)
    if order is None:
        abort(404)
    flash(f"Order {reference} is {order_status(order['status']).lower()}; "
          "only paid orders can be marked shipped.", "notice")
    return redirect(url_for("admin_orders"))


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


# --- Security headers --------------------------------------------------------
# Escaping is the defence against cross-site scripting: Jinja turns < into
# &lt; in every {{ }}, so text from the database is shown, never run. These
# headers are the second line, for the day an escaping mistake gets through.
#
# Content-Security-Policy tells the browser where this page may load things
# from. Everything here comes from this site ('self'), and none of it is
# inline: no <script> blocks, no style= attributes, no onclick=. So the policy
# can forbid inline code outright -- and then a <script> that sneaks into a
# page through a bug is simply not run.

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",       # anything not listed below: this site only
    "script-src 'self'",        # our .js files; no inline scripts, no eval
    "style-src 'self'",         # style.css; no style= attributes
    "img-src 'self'",
    "font-src 'self'",          # self-hosted since Stage 19
    "connect-src 'self'",       # fetch() to /api/cart
    "object-src 'none'",        # no plugins, ever
    "base-uri 'self'",          # an injected <base> cannot redirect our links
    "form-action 'self'",       # forms post only here (Stage 14: add Stripe)
    # Who may show our pages inside a frame. 'self', not 'none': the layout
    # audits frame our own pages at fixed widths. Another site framing the
    # admin under a decoy button ("clickjacking") is what this stops.
    "frame-ancestors 'self'",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # The same framing rule for browsers too old to read frame-ancestors.
    "X-Frame-Options": "SAMEORIGIN",
    # Use the Content-Type we send; never guess from the bytes. Without it a
    # browser may decide a file "looks like" HTML or script and run it.
    "X-Content-Type-Options": "nosniff",
    # A link followed from here tells other sites nothing about where it was
    # clicked. An order page's URL IS its key (/order/<reference>), and by
    # default it would travel in the Referer header to any site it links to.
    "Referrer-Policy": "same-origin",
}


@app.after_request
def security_headers(response):
    """Send SECURITY_HEADERS with every response: pages, JSON, static files,
    and error pages, which go through after_request too."""
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


# --- Caching static files -----------------------------------------------------
#
# Left to Flask, every static file is sent with Cache-Control: no-cache. That
# does not mean "do not cache" -- it means "check with the server before each
# use". So every page view asked again about the stylesheet, the four scripts
# and every image, and waited for a "304 Not Modified" for each: a round trip
# per file, per page, for files that had not changed.
#
# The fix is to make a URL mean one exact set of bytes, and then let the
# browser keep it for a year without asking. Two ways a URL gets that promise:
#
#   ?v=<fingerprint>   added to every url_for('static', ...) URL below. The
#                      fingerprint is taken from the file's CONTENT, so
#                      editing the file changes the URL, and the browser
#                      fetches the new one -- it never sees the old URL again.
#   a write-once name  uploads (random names, never overwritten -- Stage 17)
#                      and fonts (upstream version in the name). style.css
#                      refers to the fonts by name, where url_for cannot add
#                      a ?v, which is why they need the naming rule instead.

ONE_YEAR = 365 * 24 * 60 * 60
_WRITE_ONCE_PREFIXES = ("fonts/", "images/artworks/")
_static_versions = {}   # file path -> ((mtime, size), fingerprint)


def static_version(filename):
    """A short fingerprint of a static file's content, or None if it is missing.

    Hashing a file on every url_for would read it again for every link on
    every page. So the fingerprint is kept, and recomputed only when the
    file's modification time or size says it may have changed.
    """
    path = Path(app.static_folder) / filename
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _static_versions.get(path)
    if cached and cached[0] == key:
        return cached[1]
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    _static_versions[path] = (key, fingerprint)
    return fingerprint


@app.url_defaults
def version_static_urls(endpoint, values):
    """Add ?v=<fingerprint> to every url_for('static', ...) URL.

    url_defaults runs inside url_for itself, so every template, the srcset
    filter and the API's image URLs get it without any of them changing.
    """
    if endpoint == "static" and "filename" in values and "v" not in values:
        version = static_version(values["filename"])
        if version:
            values["v"] = version


@app.after_request
def long_cache_for_static(response):
    """Let the browser keep a static file for a year -- only when its URL
    can never mean different bytes.

    A ?v that does NOT match the file's current fingerprint (a page cached
    from before an edit, asking for the old version) gets the ordinary
    no-cache answer: caching today's bytes for a year under yesterday's
    name would be exactly the mistake this is avoiding.

    Only for a file actually served (200) or confirmed unchanged (304). A
    404 -- including a "../" path, which Flask's static view refuses before
    this runs -- is never fingerprinted.
    """
    if request.endpoint != "static" or response.status_code not in (200, 304):
        return response
    filename = (request.view_args or {}).get("filename", "")
    if (filename.startswith(_WRITE_ONCE_PREFIXES)
            or request.args.get("v") == static_version(filename)):
        response.cache_control.no_cache = None
        response.cache_control.public = True
        response.cache_control.max_age = ONE_YEAR
        # immutable: do not even revalidate when the visitor presses reload.
        response.cache_control.immutable = True
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
    if len(username) > MAX_USERNAME_LENGTH:
        raise click.BadParameter(f"keep it to {MAX_USERNAME_LENGTH} characters")

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


@app.cli.command("rebuild-renditions")
def rebuild_renditions_command():
    """Make any renditions that are missing, for every uploaded image.

        flask --app app rebuild-renditions

    Needed when RENDITION_WIDTHS changes, and for images uploaded before
    renditions existed. Safe to run any number of times: it only ever
    creates files that are not there, and never touches an original.
    """
    rows = get_db().execute(
        "SELECT id, image FROM artworks WHERE image LIKE 'artworks/%'").fetchall()
    made = 0
    for row in rows:
        original = image_file(row["image"])
        # Our own file, re-encoded at upload -- but it could have been
        # deleted by hand, and one missing file should not stop the rest.
        try:
            with Image.open(original) as image:
                image.load()
                colour_profile = image.info.get("icc_profile")
                missing = [w for w in rendition_widths(image.width)
                           if not image_file(rendition_path(row["image"], w)).exists()]
                if not missing:
                    continue
                renditions = make_renditions(image, colour_profile)
        except OSError as error:
            click.echo(f"#{row['id']}: cannot read {row['image']} ({error})", err=True)
            continue
        for width in missing:
            with open(image_file(rendition_path(row["image"], width)), "xb") as file:
                file.write(renditions[width])
            made += 1
        click.echo(f"#{row['id']}: made {', '.join(f'{w}px' for w in missing)}")
    click.echo(f"{made} rendition(s) made for {len(rows)} uploaded image(s).")


@app.cli.command("sweep-uploads")
@click.option("--delete", is_flag=True,
              help="Delete the stray files. Without this, only list them.")
def sweep_uploads_command(delete):
    """List uploaded files that no artwork uses; with --delete, remove them.

        flask --app app sweep-uploads            (look)
        flask --app app sweep-uploads --delete   (and remove)

    Strays should be rare: a crash between writing a file and saving its
    row, or a file that would not delete when its work changed. Listing is
    the default because deleting cannot be undone -- look first.

    Three kinds of file are never touched: any file whose name this site
    would not have generated, anything younger than SWEEP_MIN_AGE_SECONDS
    (it may belong to a save still in progress), and of course any file a
    row still uses.
    """
    if not UPLOAD_DIR.is_dir():
        click.echo("No upload folder yet; nothing to sweep.")
        return

    used = {Path(row["image"]).stem for row in get_db().execute(
        "SELECT image FROM artworks WHERE image LIKE 'artworks/%'")}
    cutoff = time.time() - SWEEP_MIN_AGE_SECONDS
    strays, young, foreign = [], [], []
    for path in sorted(UPLOAD_DIR.iterdir()):
        match = _UPLOAD_NAME.fullmatch(path.name)
        if not match or not path.is_file():
            foreign.append(path)
        elif match[1] in used:
            continue
        elif path.stat().st_mtime > cutoff:
            young.append(path)
        else:
            strays.append(path)

    for path in foreign:
        click.echo(f"left alone (not a name this site writes): {path.name}")
    for path in young:
        click.echo(f"left alone (too recent to be sure): {path.name}")
    for path in strays:
        if delete:
            try:
                path.unlink()
                click.echo(f"deleted: {path.name}")
            except OSError as error:
                click.echo(f"could not delete {path.name}: {error}", err=True)
        else:
            click.echo(f"stray: {path.name}")

    if strays and not delete:
        click.echo(f"{len(strays)} stray file(s). Run again with --delete to remove them.")
    elif not strays:
        click.echo("No stray files.")


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


@app.errorhandler(413)
def request_too_large(error):
    """A request body over MAX_CONTENT_LENGTH -- in practice, a huge upload.

    The form cannot be shown again with what was typed: Werkzeug refused the
    body without reading it, so there is nothing to put back.
    """
    if request.path.startswith("/api/"):
        return api_error(413, "The request is too large.")
    return render_template("413.html",
                           max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024)), 413


if __name__ == "__main__":
    app.run(debug=True, port=5000)
