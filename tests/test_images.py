"""
Are image sizes read from the files -- and is the admin unable to override them?

Run it:

    python tests/test_images.py

The sizes matter because every <img> is written with width= and height=, so
the browser can reserve the right-shaped space before the file arrives. A
wrong number means the page jumps as it loads, or the image is squashed.
"""

import sys
from contextlib import contextmanager

from support import (PROJECT_ROOT, SITE_SEED, TEST_SEED, Results, create_admin,
                     direct_connection, log_in, temp_database, temp_folder)

import app

SVG = '<svg xmlns="http://www.w3.org/2000/svg" {attributes}></svg>'


@contextmanager
def temp_placeholders(files):
    """Point the app at a placeholder folder holding exactly these files.

    Same idea as temp_database(): the test never writes into the real
    static/images/placeholders, and the finally puts the path back.
    """
    original = app.PLACEHOLDER_DIR
    with temp_folder() as folder:
        for name, text in files.items():
            (folder / name).write_text(text, encoding="utf-8")
        app.PLACEHOLDER_DIR = folder
        try:
            yield folder
        finally:
            app.PLACEHOLDER_DIR = original


def reading_svg(results):
    print("  Reading the size out of an SVG")
    cases = {
        'width="900" height="1100"': (900, 1100),
        'width="900px" height="1100px"': (900, 1100),
        # No width/height: the viewBox's last two numbers are the size.
        'viewBox="0 0 1300 800"': (1300, 800),
        'viewBox="0,0,1300,800"': (1300, 800),
        # A percentage is not a size, so the viewBox wins.
        'width="100%" height="100%" viewBox="0 0 700 1200"': (700, 1200),
        'width="850.4" height="1049.6"': (850, 1050),
        # Nothing usable at all.
        'width="100%"': None,
        '': None,
        # Zero, and absurdly large: refused, not stored.
        'width="0" height="10"': None,
        'width="99999" height="10"': None,
    }
    with temp_folder() as folder:
        for attributes, expected in cases.items():
            path = folder / "test.svg"
            path.write_text(SVG.format(attributes=attributes), encoding="utf-8")
            results.check(f"<svg {attributes}>", app.image_size(path), expected)

        not_svg = folder / "not.svg"
        not_svg.write_text('<html width="900" height="1100"></html>', encoding="utf-8")
        results.check("an XML file that is not an SVG", app.image_size(not_svg), None)

        broken = folder / "broken.svg"
        broken.write_text('<svg width="900"', encoding="utf-8")
        results.check("a file that is not valid XML", app.image_size(broken), None)

        results.check("a file that does not exist",
                      app.image_size(folder / "missing.svg"), None)


def seed_matches_files(results, seed):
    """The seeded sizes were typed by hand in a seed file. Check them against
    the files, so a placeholder redrawn at a new size cannot go unnoticed.

    A rule, not a value: it holds for any content, so it runs over the
    tests' seed AND the site's, whose sizes nothing else checks."""
    print(f"  Every artwork in {seed.relative_to(PROJECT_ROOT).as_posix()}"
          " has its file's size stored")
    with direct_connection() as connection:
        rows = connection.execute(
            "SELECT id, image, image_width, image_height FROM artworks").fetchall()
    for row in rows:
        path = PROJECT_ROOT / "static" / "images" / row["image"]
        results.check(f"artwork {row['id']} ({row['image']})",
                      (row["image_width"], row["image_height"]),
                      app.image_size(path))


def form_cannot_override(results):
    print("  The size saved is the file's, whatever the form sends")
    create_admin()
    client = app.app.test_client()
    log_in(client)

    form = {
        "artist_id": "1", "title": "Sized Work", "medium": "Oil on Canvas",
        "category": "Painting", "description": "Placeholder artwork description.",
        "price": "100", "inventory_quantity": "1", "display_order": "100",
        "image": "placeholders/artwork-01.svg",
        # A hand-written POST can include anything. These must be ignored.
        "image_width": "1", "image_height": "1",
    }
    response = client.post("/admin/artworks/new", data=form)
    results.check("the form is accepted", response.status_code, 302)
    with direct_connection() as connection:
        row = connection.execute(
            "SELECT image_width, image_height FROM artworks WHERE title = 'Sized Work'"
        ).fetchone()
    results.check("the stored size is the file's, not the POST's",
                  (row["image_width"], row["image_height"]), (900, 1100))

    page = client.get("/admin/artworks/new").get_data(as_text=True)
    results.check("the menu shows each file's size",
                  "placeholders/artwork-01.svg — 900 × 1100 px" in page, True)


def unreadable_file(results):
    print("  A placeholder whose size cannot be read")
    create_admin()
    client = app.app.test_client()
    log_in(client)

    files = {"good.svg": SVG.format(attributes='width="400" height="300"'),
             "bad.svg": SVG.format(attributes='width="100%"'),
             "notes.txt": "not an image"}
    with temp_placeholders(files):
        results.check("the menu offers the SVGs, and only the SVGs",
                      list(app.image_choices()),
                      ["placeholders/bad.svg", "placeholders/good.svg"])

        page = client.get("/admin/artworks/new").get_data(as_text=True)
        results.check("the unreadable one is listed, and says so",
                      "placeholders/bad.svg — size unreadable" in page, True)

        form = {
            "artist_id": "1", "title": "Unsized Work", "medium": "Oil on Canvas",
            "category": "Painting", "description": "Placeholder artwork description.",
            "price": "100", "inventory_quantity": "1", "display_order": "100",
            "image": "placeholders/bad.svg",
        }
        response = client.post("/admin/artworks/new", data=form)
        html = response.get_data(as_text=True)
        results.check("choosing it is a 400", response.status_code, 400)
        results.check("...with the reason on the image field",
                      "size cannot be read" in html, True)


def main():
    results = Results()

    reading_svg(results)
    print()
    for seed in (TEST_SEED, SITE_SEED):
        with temp_database(seed):
            seed_matches_files(results, seed)
        print()
    for case in (form_cannot_override, unreadable_file):
        with temp_database():
            case(results)
        print()

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
