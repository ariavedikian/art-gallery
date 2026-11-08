"""
Is every fact the site shows cited to a source, and is the site's content
free of placeholders -- while the tests' own seed stays free of real content?

Run it:

    python tests/test_content.py

database/seed.sql is the site's real content (Stage 21). No test takes an
expected VALUE from it: values come from tests/seed.sql. But some rules hold
for any content, and this file checks them against the real thing:

- every fact about an artist or a work is cited to a source
- nothing in it is a placeholder, in text or in pictures
- every source is used, and a web source is an http(s) address with the date
  it was read
- the portraits are the size the templates assume
- the pages that show it load, list their sources, and describe the neutral
  picture honestly

And the other way round: tests/seed.sql never gains a real name. Last, the
facts a citation may name are the same list in app.py and in schema.sql.

Two things are deliberately not cited: alt text (a description of the
picture, not a claim about the work) and category (the gallery's own filing,
used by the filters). Prices, stock and running order are the gallery's
decisions, not facts about the work.
"""

import re
import sys
from datetime import date

from support import (PROJECT_ROOT, SITE_SEED, TEST_SEED, Results, create_admin,
                     direct_connection, get_page, log_in, temp_database)

import app
# Jinja's own escaping function. It writes every " as &#34;, even in plain
# text; Python's html.escape(quote=False) leaves it alone, and a citation
# with quotes in it then looks missing from a page that shows it.
from markupsafe import escape  # noqa: E402

PLACEHOLDER_TEXT = re.compile(r"placeholder|artist one|artist two|artwork title", re.I)
REAL_NAMES = ("Jansem", "Carzou")
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# The size index.html and artist.html write for every portrait, until the
# portrait's size moves into the artists table (Stage 21 Part 7).
PORTRAIT_SIZE = (800, 1000)


def column(field):
    """The column a citable artwork fact lives in: the attribution is artist_id."""
    return "artist_id" if field == "artist" else field


def every_fact_cited(results):
    print("  Every fact in database/seed.sql is cited")
    with direct_connection() as db:
        for artist in db.execute("SELECT * FROM artists"):
            for field in app.ARTIST_FIELDS:
                if artist[field] is None:
                    continue        # unknown, so not stated, so nothing to cite
                cited = db.execute("SELECT COUNT(*) FROM artist_citations"
                                   " WHERE artist_id = ? AND field = ?",
                                   (artist["id"], field)).fetchone()[0]
                results.check(f"{artist['name']}: {field}", cited > 0, True)
        for work in db.execute("SELECT * FROM artworks"):
            for field in app.ARTWORK_FIELDS:
                if work[column(field)] is None:
                    continue
                cited = db.execute("SELECT COUNT(*) FROM artwork_citations"
                                   " WHERE artwork_id = ? AND field = ?",
                                   (work["id"], field)).fetchone()[0]
                results.check(f"work {work['id']}: {field}", cited > 0, True)


def no_placeholders(results):
    print("  Nothing in database/seed.sql is a placeholder")
    found = []
    with direct_connection() as db:
        for table in ("artists", "artworks", "sources", "artist_citations",
                      "artwork_citations"):
            for row in db.execute(f"SELECT * FROM {table}"):
                for key in row.keys():
                    value = row[key]
                    if not isinstance(value, str):
                        continue
                    if key in ("portrait", "image"):
                        # The neutral picture lives beside the placeholders,
                        # but says what is true: it is the one allowed.
                        if value.startswith("placeholders/") and value != app.NO_IMAGE:
                            found.append(f"{table}.{key} = {value!r}")
                    elif PLACEHOLDER_TEXT.search(value):
                        found.append(f"{table}.{key} = {value!r}")
    results.check("placeholder text or pictures", found, [])


def sources_complete(results):
    print("  Every source is cited, and a web source is a web address, dated")
    with direct_connection() as db:
        for source in db.execute("SELECT * FROM sources"):
            uses = db.execute(
                "SELECT (SELECT COUNT(*) FROM artist_citations WHERE source_id = :id)"
                " + (SELECT COUNT(*) FROM artwork_citations WHERE source_id = :id)",
                {"id": source["id"]}).fetchone()[0]
            results.check(f"{source['ref']}: supports at least one fact", uses > 0, True)
            if source["url"] is None:
                continue
            # http:// is allowed for a site that has no https (the Azumino
            # museum). What must never get through is anything else in an
            # href: javascript:, data: and the like.
            results.check(f"{source['ref']}: http(s)://",
                          source["url"].startswith(("https://", "http://")), True)
            accessed = source["accessed"] or ""
            dated = (ISO_DATE.fullmatch(accessed) is not None
                     and date.fromisoformat(accessed) <= date.today())
            results.check(f"{source['ref']}: the date it was read ({accessed!r})",
                          dated, True)


def portraits_fit_templates(results):
    print("  Every portrait is the size the templates write (800 x 1000)")
    with direct_connection() as db:
        for artist in db.execute("SELECT name, portrait FROM artists"):
            path = PROJECT_ROOT / "static" / "images" / artist["portrait"]
            results.check(f"{artist['name']}: {artist['portrait']}",
                          app.image_size(path), PORTRAIT_SIZE)


def no_image_alt(page):
    """The alt text of every <img> on the page showing the neutral picture."""
    return [re.search(r'alt="([^"]*)"', tag).group(1)
            for tag in re.findall(r"<img[^>]*" + re.escape(app.NO_IMAGE) + r"[^>]*>", page)]


def pages_show_it(results):
    print("  The pages load with this content and list their sources")
    client = app.app.test_client()
    with direct_connection() as db:
        artists = db.execute("SELECT id, slug, name FROM artists").fetchall()
        works = [row["id"] for row in db.execute("SELECT id FROM artworks")]

        def cited(table, subject, subject_id):
            return [row["citation"] for row in db.execute(
                f"SELECT DISTINCT s.citation FROM {table} c"
                f" JOIN sources s ON s.id = c.source_id WHERE c.{subject} = ?",
                (subject_id,))]

        expected = {f"/artists/{a['slug']}": cited("artist_citations", "artist_id", a["id"])
                    for a in artists}
        expected.update({f"/artwork/{w}": cited("artwork_citations", "artwork_id", w)
                         for w in works})

    for path in ("/", "/gallery"):
        page = get_page(client, path, results).get_data(as_text=True)
        alts = no_image_alt(page)
        results.check(f"{path}: the neutral picture's alt says so",
                      sorted(set(alts)), [app.NO_IMAGE_ALT] if alts else [])
    results.check("/api/artworks", client.get("/api/artworks").status_code, 200)

    for path, citations in expected.items():
        page = get_page(client, path, results).get_data(as_text=True)
        missing = [c for c in citations if str(escape(c)) not in page]
        results.check(f"{path}: lists its {len(citations)} source(s)", missing, [])
        alts = no_image_alt(page)
        results.check(f"{path}: the neutral picture's alt says so",
                      sorted(set(alts)), [app.NO_IMAGE_ALT] if alts else [])


def main_figure(page):
    """The work's own <figure> on its page, without the related works' cards."""
    return re.search(r'<figure class="mat artwork-detail__figure">.*?</figure>',
                     page, re.S).group(0)


def works_shown_properly(results):
    print("  Every photo of a work exists, is described, and is credited")
    with direct_connection() as db:
        works = db.execute("SELECT id, title, image, image_width, image_height, alt_text"
                           " FROM artworks").fetchall()
    photos = [work for work in works if app.is_photograph(work["image"])]
    results.check("at least one work has a photo", bool(photos), True)
    client = app.app.test_client()

    for work in photos:
        results.check(f"work {work['id']}: the size the seed says",
                      app.image_size(app.image_file(work["image"])),
                      (work["image_width"], work["image_height"]))
        missing = [width for width in app.rendition_widths(work["image_width"])
                   if not app.image_file(app.rendition_path(work["image"], width)).is_file()]
        results.check(f"work {work['id']}: every smaller copy exists", missing, [])
        results.check(f"work {work['id']}: alt text is written",
                      bool(work["alt_text"]), True)
        page = get_page(client, f"/artwork/{work['id']}", results).get_data(as_text=True)
        results.check(f"work {work['id']}: its picture carries the credit",
                      app.REPRODUCTION_CREDIT in main_figure(page), True)
        results.check(f"work {work['id']}: its page describes it",
                      str(escape(work["alt_text"])) in page, True)

    # Each card has the credit twice: on the card, and for the lightbox.
    printed = f">{app.REPRODUCTION_CREDIT}<"
    page = get_page(client, "/gallery", results).get_data(as_text=True)
    results.check("/gallery: a credit on each photo's card", page.count(printed), len(photos))
    results.check("/gallery: and for its lightbox",
                  page.count(f'data-credit="{app.REPRODUCTION_CREDIT}"'), len(photos))

    # The homepage's first work is the large "Selected work"; the rest are cards.
    page = get_page(client, "/", results).get_data(as_text=True)
    results.check("/: a credit on each photo", page.count(printed), len(photos))
    results.check("/: every work is on the homepage",
                  [work["id"] for work in works if str(escape(work["title"])) not in page], [])

    for work in works:
        if work["image"] == app.NO_IMAGE:
            page = get_page(client, f"/artwork/{work['id']}", results).get_data(as_text=True)
            results.check(f"work {work['id']}: the neutral picture is not credited",
                          app.REPRODUCTION_CREDIT in main_figure(page), False)


def admin_keeps_committed_photos(results):
    print("  A save in the admin keeps a committed photo, and its files")
    create_admin()
    client = app.app.test_client()
    log_in(client)
    with direct_connection() as db:
        work = db.execute("SELECT * FROM artworks WHERE image LIKE 'works/%' LIMIT 1").fetchone()
    data = {"category": work["category"], "price": "1200",
            "inventory_quantity": str(work["inventory_quantity"]),
            "loaded_inventory": str(work["inventory_quantity"]),
            "image": work["image"], "display_order": str(work["display_order"])}
    response = client.post(f"/admin/artworks/{work['id']}/edit", data=data)
    results.check("the save goes through", response.status_code, 302)
    with direct_connection() as db:
        kept = db.execute("SELECT image, price_cents FROM artworks WHERE id = ?",
                          (work["id"],)).fetchone()
    results.check("the price saved", kept["price_cents"], 120000)
    results.check("the photo is kept", kept["image"], work["image"])
    results.check("its file is still there", app.image_file(work["image"]).is_file(), True)


def field_lists_agree(results):
    print("  The facts a citation may name: app.py and schema.sql agree")
    with direct_connection() as db:
        for table, fields in (("artist_citations", app.ARTIST_FIELDS),
                              ("artwork_citations", app.ARTWORK_FIELDS)):
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name = ?",
                             (table,)).fetchone()[0]
            listed = re.search(r"CHECK \(field IN \(([^)]*)\)\)", sql).group(1)
            in_schema = re.findall(r"'([^']*)'", listed)
            results.check(table, in_schema, list(fields))


def test_seed_stays_placeholder(results):
    print("  tests/seed.sql holds no real content")
    text = TEST_SEED.read_text(encoding="utf-8").lower()
    results.check("real names in it",
                  [name for name in REAL_NAMES if name.lower() in text], [])


def main():
    results = Results()
    with temp_database(SITE_SEED):
        for case in (every_fact_cited, no_placeholders, sources_complete,
                     portraits_fit_templates, pages_show_it, works_shown_properly,
                     admin_keeps_committed_photos, field_lists_agree):
            case(results)
            print()
    test_seed_stays_placeholder(results)
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
