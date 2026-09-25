"""
Is everything a request carries treated as data, and checked before use?

Run it:

    python tests/test_input.py

Four kinds of check:

  numbers    "²" and "٣" pass str.isdigit(); neither may reach int().
  lengths    every text field has a ceiling, and a long search is not a 500.
  injection  classic SQL injection strings, sent wherever a visitor can type,
             come back as ordinary answers and change nothing.
  structure  reads app.py itself: every SQL string handed to the database is
             either fixed text or an f-string built only from names on a
             short, reviewed list.

And one input that comes from disk rather than a visitor: the database file,
which must have been built from the schema.sql this code expects.

The injection section can only try the inputs it thought of. The structure
section is the stronger guarantee: it covers every query, including ones
written after this test.
"""

import ast
import sys
from urllib.parse import quote

from support import (PROJECT_ROOT, Results, buyer, create_admin, direct_connection,
                     log_in, temp_database)

import app

SUPERSCRIPT_TWO = "²"      # "²": isdigit() is True, int() raises
ARABIC_THREE = "٣"         # "٣": isdigit() is True, int() reads 3

INJECTIONS = ["' OR '1'='1", "x' OR 1=1 --", "'; DROP TABLE artworks; --",
              '" OR ""="']


def artwork_form(**changes):
    """A valid new-artwork form, with some fields changed."""
    form = {"artist_id": "1", "title": "Artwork Title", "year": "2025",
            "medium": "Oil on Canvas", "category": "Painting",
            "description": "Placeholder description.", "price": "4800",
            "inventory_quantity": "1", "image": "placeholders/artwork-01.svg",
            "display_order": "100", "available_for_purchase": "on"}
    form.update(changes)
    return form


def count(table):
    with direct_connection() as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def numbers(results):
    print("  Numbers are ASCII digits or nothing")
    create_admin()
    client = app.app.test_client()
    log_in(client)
    before = count("artworks")

    response = client.post("/admin/artworks/new", data=artwork_form())
    results.check("a valid form is saved (the baseline)", response.status_code, 302)

    for field in ("inventory_quantity", "display_order", "artist_id"):
        for text, label in ((SUPERSCRIPT_TWO, "superscript two"),
                            (ARABIC_THREE, "Arabic-Indic three")):
            response = client.post("/admin/artworks/new",
                                   data=artwork_form(**{field: text}))
            results.check(f"{field} = {label} is refused, not a crash",
                          response.status_code, 400)

    for text in (ARABIC_THREE * 2, "4800" + SUPERSCRIPT_TWO):
        response = client.post("/admin/artworks/new", data=artwork_form(price=text))
        results.check(f"price {text.encode('unicode_escape').decode()} is refused",
                      response.status_code, 400)

    results.check("only the valid form added a work", count("artworks"), before + 1)

    # The hidden field carrying the stock the edit form loaded.
    with direct_connection() as db:
        stock = db.execute("SELECT inventory_quantity FROM artworks WHERE id = 1"
                           ).fetchone()[0]
    response = client.post("/admin/artworks/1/edit",
                           data=artwork_form(loaded_inventory=SUPERSCRIPT_TWO,
                                             inventory_quantity=str(stock)))
    results.check("loaded_inventory = superscript two is refused",
                  response.status_code, 400)

    with app.app.test_request_context():
        results.check("is_digits('0123')", app.is_digits("0123"), True)
        results.check("is_digits('')", app.is_digits(""), False)
        results.check("is_digits(' 1')", app.is_digits(" 1"), False)


def lengths(results):
    print("  Every text field has a ceiling")
    limits = app.CHECKOUT_LIMITS

    for field in limits:
        client = app.app.test_client()
        with client.session_transaction() as session:
            session["cart"] = {"1": 1}
        details = buyer()
        if field == "customer_email":
            details[field] = "a" * (limits[field] - 12 + 1) + "@example.com"
        else:
            details[field] = "A" * (limits[field] + 1)
        response = client.post("/checkout", data=details)
        results.check(f"{field} one over the limit is refused",
                      response.status_code, 400)

    # Exactly AT every limit is fine: the ceiling is not off by one. A
    # different work from the checks above (artwork 1 is a single original),
    # so this check cannot fail just because one of those let an order through.
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["cart"] = {"2": 1}
    details = buyer(email="a" * (limits["customer_email"] - 12) + "@example.com")
    details["customer_name"] = "A" * limits["customer_name"]
    details["shipping_address"] = "A" * limits["shipping_address"]
    response = client.post("/checkout", data=details)
    results.check("every field exactly at its limit is accepted",
                  response.headers.get("Location", "").startswith("/order/"), True)

    client = app.app.test_client()
    long_search = "x" * 60_000       # over SQLite's 50,000-byte LIKE limit
    response = client.get("/gallery?q=" + long_search)
    results.check("a 60,000-character search is not a 500", response.status_code, 200)
    page = response.get_data(as_text=True)
    cut = "x" * app.MAX_SEARCH_LENGTH
    results.check("the search box shows the text that was actually searched",
                  f'value="{cut}"' in page, True)
    response = client.get("/api/artworks?q=" + long_search)
    results.check("...and the API, sharing filters_from(), is fine too",
                  response.status_code, 200)

    create_admin()
    response = client.post("/admin/login",
                           data={"username": "u" * 10_000, "password": "x"})
    results.check("a 10,000-character username is a failed login",
                  response.status_code, 400)
    page = response.get_data(as_text=True)
    results.check("...which does not echo all 10,000 back",
                  "u" * (app.MAX_USERNAME_LENGTH + 1) in page, False)

    runner = app.app.test_cli_runner()
    before = count("admins")
    outcome = runner.invoke(args=["create-admin", "u" * (app.MAX_USERNAME_LENGTH + 1)],
                            input="a long enough password\n" * 2)
    results.check("create-admin refuses a username over the limit",
                  outcome.exit_code != 0, True)
    results.check("...and creates nobody", count("admins"), before)


def injection(results):
    print("  SQL injection strings are only ever data")
    create_admin()
    client = app.app.test_client()
    works = count("artworks")

    for text in INJECTIONS:
        shown = text[:14]
        response = client.get("/artists/" + quote(text, safe=""))
        results.check(f"artist slug {shown!r} is a 404", response.status_code, 404)

        response = client.get("/order/" + quote(text, safe=""))
        results.check(f"order reference {shown!r} is a 404", response.status_code, 404)

        for param in ("q", "artist", "category", "status"):
            response = client.get(f"/api/artworks?{param}=" + quote(text, safe=""))
            results.check(f"?{param}={shown!r} matches no work",
                          response.get_json()["count"], 0)

        response = client.post("/admin/login",
                               data={"username": text, "password": text})
        results.check(f"login as {shown!r} fails", response.status_code, 400)

    # In LIKE, % means "anything". Escaped, it only matches a real percent sign.
    response = client.get("/api/artworks?q=%25")
    results.check("searching for % matches nothing, not everything",
                  response.get_json()["count"], 0)

    # Stored, then shown back: the text arrives in the database exactly as typed.
    buyer_client = app.app.test_client()
    with buyer_client.session_transaction() as session:
        session["cart"] = {"1": 1}
    name = "Robert'); DROP TABLE orders; --"
    details = buyer()
    details["customer_name"] = name
    response = buyer_client.post("/checkout", data=details)
    results.check("an order in that name is placed",
                  response.headers.get("Location", "").startswith("/order/"), True)
    with direct_connection() as db:
        stored = db.execute("SELECT customer_name FROM orders").fetchone()[0]
    results.check("...and the name is stored exactly as typed", stored, name)

    results.check("every work is still there", count("artworks"), works)
    results.check("the orders table is still there", count("orders"), 1)


def schema_version(results):
    print("  A database built from an older schema.sql is refused, by name")
    client = app.app.test_client()

    with temp_database():
        with direct_connection() as db:
            built = db.execute("PRAGMA user_version").fetchone()[0]
        results.check("schema.sql writes the version app.py expects",
                      built, app.SCHEMA_VERSION)
        results.check("a fresh build is accepted", client.get("/").status_code, 200)

    # Every temp_database() is a new file, so this one has not been checked yet.
    with temp_database():
        with direct_connection() as db:
            db.execute("PRAGMA user_version = 0")    # as built before Stage 20
        try:
            with app.app.app_context():
                app.get_db()
            results.fail("an old build is refused (it was accepted)")
        except RuntimeError as error:
            results.check("an old build is refused, naming the fix",
                          "python init_db.py --reset" in str(error), True)

        # Rebuilt while the server runs: accepted without a restart, because
        # a failed check is never remembered as a pass.
        with direct_connection() as db:
            db.execute(f"PRAGMA user_version = {app.SCHEMA_VERSION}")
        results.check("once rebuilt, it is accepted", client.get("/").status_code, 200)


# --- Structure --------------------------------------------------------------
# The f-string pieces allowed inside SQL. Each one is text we wrote, never a
# visitor's: adding a name here is a claim that has to be checked by reading
# where it comes from.
ALLOWED_IN_SQL = {
    "_ARTIST_COLUMNS", "_ARTWORK_COLUMNS", "_ORDER_SUMMARY_SELECT",  # constants
    "where",          # search_artworks: joined from clauses written in the code
    "placeholders",   # "?, ?, ?" -- one per value, built from a count
    "columns",        # insert_artwork: _ARTWORK_WRITE_COLUMNS joined
    "assignments",    # update_artwork: "col = ?" for each of those columns
    "', '.join(_ARTWORK_WRITE_COLUMNS)",
}
SQL_CALLS = {"execute", "executemany", "executescript", "query_db"}


def sql_problems(source):
    """Every call that hands the database SQL built in a way not allowed.

    Allowed first arguments: a plain string, an f-string whose {pieces} are
    all in ALLOWED_IN_SQL, and the bare name `sql` (query_db passing on the
    string it was given). Anything else -- "..." + name, "...".format(),
    "%s" % name, an f-string with a new piece -- is reported with its line.
    """
    problems = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in SQL_CALLS:
            continue

        sql = node.args[0]
        if isinstance(sql, ast.Constant) and isinstance(sql.value, str):
            continue
        if isinstance(sql, ast.Name) and sql.id == "sql":
            continue
        if isinstance(sql, ast.JoinedStr):
            pieces = [ast.unparse(part.value) for part in sql.values
                      if isinstance(part, ast.FormattedValue)]
            unknown = [piece for piece in pieces if piece not in ALLOWED_IN_SQL]
            if not unknown:
                continue
            problems.append(f"line {node.lineno}: {{{', '.join(unknown)}}} in SQL")
        else:
            problems.append(f"line {node.lineno}: SQL built as {type(sql).__name__}")
    return problems


def structure(results, source=None):
    print("  Every query in app.py keeps SQL and values apart")
    if source is None:
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    problems = sql_problems(source)
    for problem in problems:
        results.fail(problem)
    if not problems:
        calls = sum(1 for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.Call) and getattr(
                        node.func, "attr", getattr(node.func, "id", None)) in SQL_CALLS)
        results.ok(f"all {calls} database calls pass SQL we wrote")

    # Read from the parsed code, not the text, so a comment explaining why
    # isdigit() is wrong does not count as using it.
    uses = [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Attribute) and node.attr == "isdigit"]
    results.check("lines calling str.isdigit() (use is_digits)", uses, [])


def main():
    results = Results()

    for case in (numbers, lengths, injection):
        with temp_database():
            case(results)
        print()
    schema_version(results)
    print()
    structure(results)

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
