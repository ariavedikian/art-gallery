"""
Art Gallery — a Flask web application.

Stage 12: checkout.

HTTP is stateless — two requests from the same visitor arrive as strangers —
so a cart has to be stored somewhere and handed back with every request. This
one lives in the Flask session: a cookie in the visitor's browser, signed with
SECRET_KEY so it cannot be edited without the signature failing.

The cookie holds one thing: {artwork_id: quantity}. Titles, prices and
availability are read from the database on every request, so a price can never
arrive from the client.

Checkout turns that cart into an order inside a single transaction: the
inventory is claimed and the order is written together, or neither happens.
The payment step is a clearly-labelled MOCK until Stage 14.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)

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


@app.route("/gallery")
def gallery():
    # request.args is the query string: /gallery?artist=artist-two&q=oil
    # .get() with a default turns a missing parameter into an empty filter,
    # so a bare /gallery and a cleared form take the same path.
    filters = {
        "q": request.args.get("q", "").strip(),
        "artist": request.args.get("artist", ""),
        "category": request.args.get("category", ""),
        "status": request.args.get("status", ""),
        "price": request.args.get("price", ""),
    }

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

    # The same `status` column the price line and the availability filter
    # read. The button is only rendered for a work that is for sale, but a
    # POST can be sent without ever loading that page, so the server checks
    # again. A rule enforced only in the template is not enforced.
    if artwork["status"] != "for-sale":
        flash("That work is not available to buy.", "error")
        return redirect(url_for("artwork_page", artwork_id=artwork["id"]))

    cart = get_cart()
    key = str(artwork["id"])
    allowed = allowed_quantity(artwork)
    wanted = cart.get(key, 0) + max(quantity, 1)

    if wanted > allowed:
        wanted = allowed
        flash(f"Only {allowed} of that work can be added. Your cart now "
              f"holds {allowed}.", "notice")
    else:
        flash("Added to your cart.", "success")

    cart[key] = wanted
    save_cart(cart)

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

    return redirect(url_for("order_page", reference=reference))


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


@app.route("/about")
def about():
    return "Placeholder gallery description."


@app.route("/health")
def health():
    return {"status": "ok", "stage": 12}


# --- Error handlers ----------------------------------------------------------

@app.errorhandler(404)
def page_not_found(error):
    """Render our own 404 page instead of the plain Werkzeug one.

    Returning a tuple sets the status code explicitly. Returning just the
    template would send 200 OK with a page saying "not found", which lies to
    browsers, search engines and monitoring tools. The status code is part of
    the answer, not decoration.
    """
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)
