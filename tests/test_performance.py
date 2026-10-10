"""
Does the site avoid work it does not need to do?

Run it:

    python tests/test_performance.py

Four kinds of waste Stage 19 removed, each pinned here:

- asking the server about unchanged static files on every page (caching)
- two extra connections, and every visitor's IP, for fonts (self-hosting)
- reading every order line to answer "has this work sold?" (an index)
- a query per artwork, or lazy-loading what is already on screen

Timings are not measured -- they vary with the machine. What is checked is
the structure that makes the site fast, which does not.
"""

import re
import shutil
import sqlite3
import sys
from contextlib import contextmanager

from support import (PROJECT_ROOT, Results, direct_connection, get_page,
                     temp_database, temp_folder)

import app

STATIC = PROJECT_ROOT / "static"
VERSIONED = re.compile(r"/static/([^\"?]+)\?v=([0-9a-f]{12})")


@contextmanager
def temp_static():
    """Serve static files from a throwaway copy, so a test can edit one."""
    original = app.app.static_folder
    with temp_folder() as folder:
        copy = folder / "static"
        shutil.copytree(STATIC, copy, ignore=shutil.ignore_patterns("artworks"))
        app.app.static_folder = str(copy)
        try:
            yield copy
        finally:
            app.app.static_folder = original


def caching(results):
    print("  Static files: fingerprinted URLs, cached for a year")
    client = app.app.test_client()
    html = client.get("/").get_data(as_text=True)
    urls = VERSIONED.findall(html)
    unversioned = re.findall(r'(?:href|src)="(/static/[^"?]+)"', html)
    results.check("every static URL on the homepage carries ?v=", unversioned, [])
    results.check("...each fingerprint is the file's own",
                  all(app.static_version(name) == v for name, v in urls), True)

    css = next((f"/static/{n}?v={v}" for n, v in urls if n.endswith("style.css")), None)
    if css is None:
        results.fail("the stylesheet has a fingerprinted URL to test")
        return
    header =lambda url: client.get(url).headers.get("Cache-Control", "")
    results.check("the fingerprinted stylesheet: a year, immutable",
                  header(css), "public, max-age=31536000, immutable")
    results.check("the same file without ?v: ask every time", header(css.split("?")[0]), "no-cache")
    results.check("...or with a stale ?v: ask every time",
                  header(css.split("?")[0] + "?v=000000000000"), "no-cache")
    results.check("a font (write-once name): a year, immutable",
                  header("/static/fonts/inter-v20-latin-normal.woff2"),
                  "public, max-age=31536000, immutable")
    results.check("a missing file is a 404 with no caching promise",
                  (client.get("/static/css/nope.css").status_code, header("/static/css/nope.css")),
                  (404, ""))

    with temp_static() as copy:
        (copy / "images" / "artworks").mkdir(parents=True)
        (copy / "images" / "artworks" / ("a" * 32 + ".jpg")).write_bytes(b"x")
        results.check("an upload (write-once name): a year, immutable",
                      header("/static/images/artworks/" + "a" * 32 + ".jpg"),
                      "public, max-age=31536000, immutable")

        old = re.search(r"style\.css\?v=([0-9a-f]{12})", client.get("/").get_data(as_text=True)).group(1)
        with open(copy / "css" / "style.css", "a", encoding="utf-8") as stylesheet:
            stylesheet.write("\n/* an edit */\n")
        new = re.search(r"style\.css\?v=([0-9a-f]{12})", client.get("/").get_data(as_text=True)).group(1)
        results.check("editing the stylesheet changes its URL, so no browser "
                      "keeps the old copy", old != new, True)


def fonts(results):
    print("  Fonts: served from here, not from Google")
    client = app.app.test_client()
    html = client.get("/").get_data(as_text=True)
    results.check("no page asks Google for fonts",
                  re.findall(r"fonts\.(?:googleapis|gstatic)\.com", html), [])

    css = (STATIC / "css" / "style.css").read_text(encoding="utf-8")
    sources = re.findall(r'src: url\("\.\./fonts/([^"]+)"\)', css)
    results.check("three @font-face files", len(sources), 3)
    results.check("...every one of them exists",
                  [s for s in sources if not (STATIC / "fonts" / s).is_file()], [])
    results.check("...each named with its upstream version (write-once)",
                  [s for s in sources if not re.search(r"-v\d+-", s)], [])
    families = {name.split("-v")[0] for name in sources}
    results.check("...and each family's licence sits beside it",
                  sorted(f for f in families if not (STATIC / "fonts" / f"OFL-{f}.txt").is_file()), [])


def index(results):
    print("  Order lines are found by artwork through an index")
    with direct_connection() as connection:
        plan = [row[3] for row in connection.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM order_items WHERE artwork_id = ?", (1,))]
    results.check("count_sales() searches the index instead of scanning",
                  plan, ["SEARCH order_items USING COVERING INDEX idx_order_items_artwork_id (artwork_id=?)"])


def query_counts(results):
    print("  The number of queries does not grow with the collection")
    statements = []
    real_connect = sqlite3.connect

    def watching(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    def count(path):
        statements.clear()
        get_page(client, path, results)
        return len([s for s in statements if not s.startswith("PRAGMA")])

    client = app.app.test_client()
    app.sqlite3.connect = watching
    try:
        pages = ["/", "/gallery", "/artists/artist-one", "/artwork/1"]
        before = {page: count(page) for page in pages}
        with direct_connection() as connection:
            for n in range(30):
                connection.execute(
                    "INSERT INTO artworks (artist_id, title, medium, category, description,"
                    " price_cents, image, image_width, image_height, is_featured)"
                    " VALUES (1, ?, 'Oil', 'Painting', 'Placeholder.', 100,"
                    " 'placeholders/artwork-01.svg', 900, 1100, 1)", (f"Extra {n}",))
            connection.commit()
        after = {page: count(page) for page in pages}
    finally:
        app.sqlite3.connect = real_connect
    results.check("queries per page with 6 works, and with 36", after, before)
    results.check("...and no page needs more than 5", max(after.values()) <= 5, True)


def lazy_loading(results):
    print("  Lazy loading only for images that start off screen")
    client = app.app.test_client()

    def loading(path):
        html = client.get(path).get_data(as_text=True)
        return ["lazy" if 'loading="lazy"' in tag else "eager"
                for tag in re.findall(r"<img[^>]*>", html)
                if "lightbox-image" not in tag]

    results.check("All works: the first row (4) eager, the rest lazy",
                  loading("/gallery"), ["eager"] * 4 + ["lazy"] * 2)
    # The artist page opens with the portrait (eager, high priority); its
    # grid starts below the fold.
    results.check("an artist page: portrait eager, grid lazy",
                  loading("/artists/artist-one"), ["eager", "lazy", "lazy", "lazy"])
    with client.session_transaction() as session:
        session["cart"] = {"1": 1, "2": 1, "4": 1, "6": 1}
    results.check("the cart: the first three lines eager, the fourth lazy",
                  loading("/cart"), ["eager", "eager", "eager", "lazy"])


def main():
    results = Results()
    for case in (caching, fonts, index, query_counts, lazy_loading):
        with temp_database():
            case(results)
        print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
