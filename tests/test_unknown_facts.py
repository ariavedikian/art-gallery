"""
When a fact is unknown, does the site leave it out -- rather than show the
word "None", an empty label, or a dangling comma?

Run it:

    python tests/test_unknown_facts.py

Real content (Stage 21) has gaps the placeholders never had: a fact nobody
has verified stays out, which in the database is NULL. This file blanks every
optional fact on one artist and one work, loads every page that shows them,
and parses what comes back. Then it fills the new catalogue fields in and
checks each appears, labelled.
"""

import re
import sqlite3
import sys
from html.parser import HTMLParser

from support import (Results, create_admin, direct_connection, get_page, log_in,
                     temp_database)

import app

# The facts a real record may lack. Title, category, price and image are
# not here: every work has those.
ARTWORK_FACTS = ("year", "medium", "description", "dimensions", "edition", "inscriptions")
ARTIST_FACTS = ("lifespan", "summary", "bio")


class Reading(HTMLParser):
    """What a visitor would find wrong inside <main>: the word None, an empty
    paragraph or definition, or a separator with nothing on one side of it
    (what is left of "Artist One, 1950" when the date is unknown).

    Whole units are read, never a <span>: a card's hidden span begins with
    ", " on purpose, continuing the title, so its link is what is judged."""

    WATCHED = {"p", "dd", "dt", "a", "td"}

    # A separator with nothing on one side: at the start, at the end, or
    # straight before another separator or an opening bracket.
    STRANDED = re.compile(r"^[,·]|[,·]\s*([,·(]|$)")

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.open = []          # [tag, [text pieces]] for watched elements
        self.problems = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main = True
        if not self.in_main:
            return
        for name, value in attrs:
            if value is not None and value.strip() == "None":
                self.problems.append(f'<{tag} {name}="None">')
        # A live region (aria-live) is empty on purpose until a script
        # speaks into it, like the cart's "Added" message; it is not a fact.
        if tag in self.WATCHED:
            self.open.append([tag, [], "aria-live" in dict(attrs)])

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main = False
        if not self.in_main or tag not in self.WATCHED:
            return
        while self.open:
            name, pieces, live = self.open.pop()
            if name == tag:
                break
        else:
            return
        text = " ".join("".join(pieces).split())
        if live:
            return
        if tag in {"p", "dd", "dt"} and not text:
            self.problems.append(f"an empty <{tag}>")
        elif self.STRANDED.search(text):
            self.problems.append(f"<{tag}> {text!r}")

    def handle_data(self, data):
        if not self.in_main:
            return
        if "None" in data.split():
            self.problems.append(f"the word None in {data.strip()!r}")
        for _, pieces, _ in self.open:
            pieces.append(data)


def setup(results, description, sql):
    """Run one setup statement. If the schema refuses it, say so as a
    failure rather than crash, so the rest of the file still reports."""
    try:
        with direct_connection() as db:
            db.execute(sql)
            db.commit()
        return True
    except sqlite3.Error as error:
        results.fail(f"{description} ({error})")
        return False


def blank_everything(results):
    """Set every optional fact of work 1 and artist 1 to NULL. Each is a
    separate statement, so the schema refusing one shows up by name."""
    with direct_connection() as db:
        for fact in ARTWORK_FACTS:
            try:
                db.execute(f"UPDATE artworks SET {fact} = NULL WHERE id = 1")
                results.ok(f"the database accepts an unknown artwork {fact}")
            except sqlite3.Error as error:
                results.fail(f"the database accepts an unknown artwork {fact} ({error})")
        for fact in ARTIST_FACTS:
            try:
                db.execute(f"UPDATE artists SET {fact} = NULL WHERE id = 1")
                results.ok(f"the database accepts an unknown artist {fact}")
            except sqlite3.Error as error:
                results.fail(f"the database accepts an unknown artist {fact} ({error})")
        db.commit()


def nothing_shown_for_unknowns(results):
    print("  Unknown facts are left out of every page that shows them")
    blank_everything(results)
    create_admin()
    client = app.app.test_client()
    log_in(client)
    with client.session_transaction() as session:
        session["cart"] = {"1": 1}
    for path in ("/", "/gallery", "/gallery?q=Artwork", "/artists/artist-one",
                 "/artwork/1", "/cart", "/checkout", "/admin",
                 "/admin/artworks/1/delete"):
        html = get_page(client, path, results).get_data(as_text=True)
        results.check(f"{path}", Reading(html).problems, [])

    # The API says null, which is honest JSON for "unknown".
    work = client.get("/api/artworks/1").get_json()
    results.check("the API reports an unknown medium as null", work["medium"], None)


def search_still_finds_it(results):
    print("  Search finds a work whose other facts are unknown")
    if not setup(results, "a work with an unknown medium and description",
                 "UPDATE artworks SET title = 'Searchable', medium = NULL,"
                 " description = NULL, year = NULL WHERE id = 1"):
        return
    page = app.app.test_client().get("/gallery?q=Searchable").get_data(as_text=True)
    # title LIKE ? OR medium LIKE ?: TRUE OR NULL is TRUE, so a NULL medium
    # must not hide a work whose title matches.
    results.check("found by its title", 'href="/artwork/1"' in page, True)


def admin_saves_unknowns(results):
    print("  The admin form saves a blank medium and description as unknown")
    create_admin()
    client = app.app.test_client()
    log_in(client)
    form = {"artist_id": "1", "title": "Barely Known", "year": "", "medium": "",
            "category": "Painting", "description": "", "price": "100",
            "inventory_quantity": "1", "image": "placeholders/artwork-01.svg",
            "display_order": "5", "alt_text": ""}
    response = client.post("/admin/artworks/new", data=form)
    results.check("the form is accepted", response.status_code, 302)
    with direct_connection() as db:
        row = db.execute("SELECT year, medium, description FROM artworks"
                         " WHERE title = 'Barely Known'").fetchone()
    # NULL, not '': an empty string would claim the medium is known to be blank.
    results.check("stored as NULL, not ''",
                  tuple(row) if row else None, (None, None, None))


def catalogue_fields_shown(results):
    print("  Dimensions, edition and inscriptions appear, labelled, when known")
    if not setup(results, "the catalogue fields exist",
                 "UPDATE artworks SET dimensions = 'Placeholder dimensions',"
                 " edition = 'Placeholder edition',"
                 " inscriptions = 'Placeholder inscription' WHERE id = 2"):
        return
    page = app.app.test_client().get("/artwork/2").get_data(as_text=True)
    for label, value in (("Dimensions", "Placeholder dimensions"),
                         ("Edition", "Placeholder edition"),
                         ("Inscriptions", "Placeholder inscription")):
        results.check(f"{label}: {value}",
                      f"<dt>{label}</dt><dd>{value}</dd>" in page, True)
    # Work 2 is twelve copies of a print. That is stock, not an edition: a
    # print numbered 23/150 is one object from an edition of 150.
    results.check("its stock is labelled as stock",
                  "<dt>Available</dt><dd>12 copies</dd>" in page, True)
    page = app.app.test_client().get("/artwork/6").get_data(as_text=True)
    results.check("no Edition row for a work whose edition is unknown",
                  "<dt>Edition</dt>" in page, False)


def main():
    results = Results()
    for case in (nothing_shown_for_unknowns, search_still_finds_it,
                 admin_saves_unknowns, catalogue_fields_shown):
        with temp_database():
            case(results)
        print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
