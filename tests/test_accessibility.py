"""
Does every page keep the structure assistive technology relies on?

Run it:

    python tests/test_accessibility.py

Stage 19 audited every page in a browser and found the structure sound: one
<h1>, no skipped heading levels, every image with alt text, every form
control labelled, no duplicate ids, every ARIA reference pointing at
something real. This file keeps it that way, page by page, with the stdlib
HTML parser -- no browser needed, so it runs with the rest of the suite.

Contrast and focus visibility need a real browser and are audited there.

It also covers alt text as data (Stage 19): written in the admin, falling
back to "<title> by <artist>", never hard-coded in a template.
"""

import re
import sys
from html.parser import HTMLParser

from support import (PROJECT_ROOT, Results, create_admin, direct_connection,
                     get_page, log_in, place_order, temp_database)

import app

CONTROLS = {"input", "select", "textarea"}
UNLABELLED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}
REFERENCE_ATTRIBUTES = ("aria-describedby", "aria-labelledby", "aria-controls", "for")


class PageStructure(HTMLParser):
    """Collects what the checks need from one page."""

    def __init__(self):
        super().__init__()
        self.headings, self.images, self.controls = [], [], []
        self.ids, self.references, self.label_targets = [], [], set()
        self._label_depth = 0
        self._in_captioned_figure = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for name in REFERENCE_ATTRIBUTES:
            for target in (attrs.get(name) or "").split():
                self.references.append((name, target))
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        elif tag == "figure" and "admin-form__current" in (attrs.get("class") or ""):
            self._in_captioned_figure = True
        elif tag == "img":
            self.images.append(dict(attrs, captioned=self._in_captioned_figure))
        elif tag == "label":
            self._label_depth += 1
            if attrs.get("for"):
                self.label_targets.add(attrs["for"])
        elif tag in CONTROLS and attrs.get("type") not in UNLABELLED_INPUT_TYPES:
            self.controls.append((attrs, self._label_depth > 0))

    def handle_endtag(self, tag):
        if tag == "label":
            self._label_depth -= 1
        elif tag == "figure":
            self._in_captioned_figure = False


def structure_problems(html):
    page = PageStructure()
    page.feed(html)
    problems = []

    if page.headings.count(1) != 1:
        problems.append(f"{page.headings.count(1)} <h1> elements")
    for before, after in zip(page.headings, page.headings[1:]):
        if after > before + 1:
            problems.append(f"heading jumps from h{before} to h{after}")

    for image in page.images:
        if "alt" not in image:
            problems.append(f"<img> without alt: {image.get('src')}")
        # alt="" says "decoration, skip me". Only two images may say that:
        # the lightbox's (filled in by script when it opens) and the admin
        # form's thumbnail, whose caption describes it.
        elif image["alt"] == "" and image.get("id") != "lightbox-image" \
                and not image["captioned"]:
            problems.append(f"empty alt on {image.get('src')}")

    for attrs, wrapped in page.controls:
        if not (wrapped or attrs.get("id") in page.label_targets
                or attrs.get("aria-label") or attrs.get("aria-labelledby")):
            problems.append(f"unlabelled <{attrs.get('name')}>")

    duplicates = {i for i in page.ids if page.ids.count(i) > 1}
    if duplicates:
        problems.append(f"duplicate ids {sorted(duplicates)}")
    for name, target in page.references:
        if target not in page.ids:
            problems.append(f'{name}="{target}" points at nothing')
    return problems


def every_page(results):
    print("  The structure of every page")
    create_admin()
    client, reference = place_order(artwork_id=2)
    with client.session_transaction() as session:
        session["cart"] = {"4": 1}
    log_in(client)
    pages = ["/", "/gallery", "/gallery?availability=sold", "/artists/artist-one",
             "/artwork/1", "/artwork/3", "/cart", "/checkout", f"/order/{reference}",
             "/orders", "/no-such-page", "/admin", "/admin/artworks/new",
             "/admin/artworks/2/edit", "/admin/artworks/2/delete", "/admin/orders"]
    for path in pages:
        problems = structure_problems(get_page(client, path, results).get_data(as_text=True))
        results.check(f"{path}", problems, [])

    # A rejected form adds error messages and aria-describedby links to them.
    response = client.post("/admin/artworks/new", data={"title": ""})
    results.check("a rejected admin form (errors wired up)",
                  structure_problems(response.get_data(as_text=True)), [])
    response = client.post("/checkout", data={"customer_email": "nope"})
    results.check("a rejected checkout form",
                  structure_problems(response.get_data(as_text=True)), [])


def no_wording_in_templates(results):
    """Stage 21 swaps placeholder content for real content by changing data.
    A template that says "Placeholder image of..." would have to change too."""
    print("  Alt text is data: no template or script writes it")
    offenders = []
    for folder, pattern in (("templates", "**/*.html"), ("static/js", "*.js")):
        for path in (PROJECT_ROOT / folder).glob(pattern):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"Placeholder (image|portrait|hero)", text):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)}")
    results.check("no hard-coded placeholder alt wording", offenders, [])


def artwork_alt_text(results):
    print("  An artwork's alt text")
    create_admin()
    client = app.app.test_client()
    log_in(client)

    def img_alt(path, image):
        html = client.get(path).get_data(as_text=True)
        tag = re.search(rf'<img[^>]*{re.escape(image)}[^>]*>', html).group(0)
        return re.search(r'alt="([^"]*)"', tag).group(1)

    results.check("a seeded work says what its image is: a placeholder",
                  img_alt("/artwork/1", "artwork-01.svg"),
                  "Placeholder image of Artwork Title by Artist One")

    form = {"artist_id": "1", "title": "Described Work", "medium": "Oil on Canvas",
            "category": "Painting", "description": "Placeholder artwork description.",
            "price": "100", "inventory_quantity": "1", "display_order": "5",
            "image": "placeholders/artwork-05.svg",
            "alt_text": "  Two figures on a quay, dusk, in greys and ochre.  "}
    client.post("/admin/artworks/new", data=form)
    with direct_connection() as connection:
        work = connection.execute(
            "SELECT id, alt_text FROM artworks WHERE title = 'Described Work'").fetchone()
    results.check("written alt text is stored, trimmed", work["alt_text"],
                  "Two figures on a quay, dusk, in greys and ochre.")
    results.check("...and used on the artwork page",
                  img_alt(f"/artwork/{work['id']}", "artwork-05.svg"),
                  "Two figures on a quay, dusk, in greys and ochre.")
    gallery = client.get("/gallery").get_data(as_text=True)
    results.check("...and on its card, where the lightbox copies it from",
                  'alt="Two figures on a quay, dusk, in greys and ochre."' in gallery, True)

    client.post("/admin/artworks/new", data=dict(form, title="Undescribed Work", alt_text=" "))
    with direct_connection() as connection:
        work = connection.execute(
            "SELECT id, alt_text FROM artworks WHERE title = 'Undescribed Work'").fetchone()
    results.check("blank alt text is stored as NULL, not ''", work["alt_text"], None)
    results.check("...and the page falls back to title and artist, never alt=\"\"",
                  img_alt(f"/artwork/{work['id']}", "artwork-05.svg"),
                  "Undescribed Work by Artist One")

    response = client.post("/admin/artworks/new", data=dict(form, alt_text="x" * 301))
    results.check("alt text over 300 characters is refused (400)", response.status_code, 400)

    with direct_connection() as connection:
        connection.execute("UPDATE artists SET portrait_alt = NULL WHERE slug = 'artist-two'")
        connection.commit()
    results.check("a portrait without alt text falls back to \"Portrait of <name>\"",
                  img_alt("/artists/artist-two", "artist-two.svg"), "Portrait of Artist Two")


def main():
    results = Results()
    for case in (every_page, artwork_alt_text):
        with temp_database():
            case(results)
        print()
    no_wording_in_templates(results)
    print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
