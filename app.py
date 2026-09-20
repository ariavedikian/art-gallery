"""
Art Gallery — a Flask web application.

Stage 10 (part 2): the collection is filtered in SQL, from the query string.

Every page that shows artworks — the homepage, each artist page and All works
— fetches rows with SQL and renders them through one shared grid macro. Which
works appear and in what order is decided entirely by the queries here; the
templates only decide how a work looks.
"""

import sqlite3
from pathlib import Path

from flask import Flask, abort, g, render_template, request

app = Flask(__name__)

GALLERY_NAME = "Gallery Placeholder"

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

        g.db = sqlite3.connect(DATABASE_PATH)

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


# --- Template helpers --------------------------------------------------------

@app.template_filter("usd")
def usd(cents):
    """Turn 480000 into "$4,800". Money is stored as whole cents (an integer)
    because floats lose precision: 0.1 + 0.2 != 0.3 in binary arithmetic.
    Formatting is presentation, so it belongs here rather than in the data."""
    return "${:,.0f}".format(cents / 100)


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


@app.route("/about")
def about():
    return "Placeholder gallery description."


@app.route("/health")
def health():
    return {"status": "ok", "stage": 10}


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
