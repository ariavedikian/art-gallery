"""
Is text from the database always shown as text, and is the second line of
defence -- the security headers -- on every response?

Run it:

    python tests/test_output.py

The probe is text built to break out of whatever surrounds it: a quote to end
an attribute, </title> and </textarea> to end those elements, then a tag of
its own. It is written into every field a person can fill in -- through the
database for artists and works, through the forms for an order, a search and
a login -- and then every page that shows any of it is PARSED, as a browser
would. The test passes only if the probe never became an element or an
attribute, and was shown instead: present, as text, on each page.
"""

import re
import sys
from html.parser import HTMLParser

from support import (PROJECT_ROOT, Results, buyer, create_admin, direct_connection,
                     get_page, log_in, temp_database)

import app

PROBE = "\"'></title></textarea><x-probe data-probe=1>"
SHORT_PROBE = "\"><x-probe data-probe=1>"   # for year: 40 characters at most
EMAIL_PROBE = "a\"'></textarea><x-probe>@example.com"   # one @, no spaces


class Page(HTMLParser):
    """What a page turned into once parsed: its elements, attributes and text."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags, self.attrs, self.text = [], [], []
        self.feed(html)
        self.close()
        self.text = "".join(self.text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self.attrs.extend(attrs)

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        self.text.append(data)   # joined into one string once parsing ends

    def shows(self, probe):
        """The probe appears as text, or as an attribute's value."""
        return probe in self.text or any(probe in (value or "") for _, value in self.attrs)

    def escaped(self):
        return not any(tag == "x-probe" for tag, _ in self.tags) and \
               not any(name == "data-probe" for name, _ in self.attrs)


def fill_with_probes():
    """Write the probe into every text column a person can set."""
    with direct_connection() as db:
        db.execute("""UPDATE artworks SET title = ?, medium = ?, category = ?,
                      description = ?, year = ?, alt_text = ? WHERE id = 1""",
                   (PROBE, PROBE, PROBE, PROBE, SHORT_PROBE, PROBE))
        # Work 2 has no alt text of its own, so its alt is the SQL fallback,
        # "<title> by <artist>" -- built from two probes.
        db.execute("UPDATE artworks SET title = ?, alt_text = NULL WHERE id = 2",
                   (PROBE,))
        db.execute("""UPDATE artists SET name = ?, lifespan = ?, summary = ?,
                      bio = ?, portrait_alt = ? WHERE id = 1""",
                   (PROBE, SHORT_PROBE, PROBE, PROBE, PROBE))
        db.execute("UPDATE artists SET name = ?, portrait_alt = NULL WHERE id = 2",
                   (PROBE,))
        db.commit()
        return db.execute("SELECT slug FROM artists WHERE id = 1").fetchone()[0]


def pages_to_check():
    """(label, response) for every page that shows a probe, and a few more."""
    slug = fill_with_probes()
    visitor = app.app.test_client()
    pages = [(path, visitor.get(path)) for path in (
        "/", "/gallery", f"/artists/{slug}", "/artwork/1", "/artwork/2")]
    pages.append(("/gallery?q=<probe>", visitor.get("/gallery", query_string={"q": PROBE})))

    with visitor.session_transaction() as session:
        session["cart"] = {"1": 1, "2": 1}
    pages += [("/cart", visitor.get("/cart")), ("/checkout", visitor.get("/checkout"))]

    details = buyer(email=EMAIL_PROBE)
    details.update(customer_name=PROBE, shipping_address=PROBE)
    placed = visitor.post("/checkout", data=details)
    reference = placed.headers["Location"].rsplit("/", 1)[-1]
    pages += [("/order/<ref>", visitor.get(f"/order/{reference}")),
              ("/orders", visitor.get("/orders"))]

    # A rejected checkout sends everything typed back into the form.
    with visitor.session_transaction() as session:
        session["cart"] = {"2": 1}
    rejected = buyer(email=EMAIL_PROBE)
    rejected.update(customer_name=PROBE, shipping_address="")
    pages.append(("rejected checkout", visitor.post("/checkout", data=rejected)))

    stranger = app.app.test_client()
    pages.append(("failed login", stranger.post(
        "/admin/login", data={"username": PROBE, "password": "x", "next": PROBE})))

    create_admin()
    admin = app.app.test_client()
    log_in(admin)
    pages += [(path, admin.get(path)) for path in (
        "/admin", "/admin/artworks/1/edit", "/admin/artworks/1/delete",
        "/admin/orders")]

    # A new work saved from the form: the flash message quotes its title.
    new = {"artist_id": "1", "title": PROBE, "year": SHORT_PROBE, "medium": PROBE,
           "category": PROBE, "description": PROBE, "price": "10",
           "inventory_quantity": "1", "image": "placeholders/artwork-01.svg",
           "display_order": "5", "alt_text": PROBE}
    pages.append(("flash after saving a work",
                  admin.post("/admin/artworks/new", data=new, follow_redirects=True)))
    return pages


def escaping(results):
    print("  Text from the database and the forms is shown, never run")
    results.check("Jinja escapes .html templates",
                  app.app.select_jinja_autoescape("page.html"), True)

    for label, response in pages_to_check():
        page = Page(response.get_data(as_text=True))
        results.check(f"{label}: no probe became markup", page.escaped(), True)
        shown = page.shows(PROBE) or page.shows(EMAIL_PROBE)
        results.check(f"{label}: ...and it is shown as text", shown, True)

    client = app.app.test_client()
    response = client.get("/api/artworks/1")
    results.check("the API sends the title as JSON, not HTML",
                  response.mimetype, "application/json")
    results.check("...exactly as stored", response.get_json()["title"], PROBE)


def escape_hatches(results):
    print("  Nothing switches escaping off, or builds HTML from strings in JS")
    sources = {path: path.read_text(encoding="utf-8") for path in
               [PROJECT_ROOT / "app.py",
                *sorted((PROJECT_ROOT / "templates").rglob("*.html"))]}
    hatches = re.compile(r"\|\s*safe\b|Markup\(|autoescape\s+false|\|\s*unescape\b")
    found = [f"{path.name}: {match.group()}" for path, text in sources.items()
             for match in hatches.finditer(text)]
    results.check("|safe, Markup() or autoescape false in app.py and templates",
                  found, [])

    # Assignments and calls only: a comment explaining innerHTML is fine.
    sinks = re.compile(r"\.(innerHTML|outerHTML)\s*=[^=]|insertAdjacentHTML\s*\(|"
                       r"document\.write\s*\(|\beval\s*\(|new\s+Function\s*\(")
    found = [f"{path.name}: {match.group().strip()}"
             for path in sorted((PROJECT_ROOT / "static" / "js").glob("*.js"))
             for match in sinks.finditer(path.read_text(encoding="utf-8"))]
    results.check("scripts that turn strings into HTML or code", found, [])


def headers(results):
    print("  Every response carries the security headers")
    policy = app.CONTENT_SECURITY_POLICY
    for word in ("'unsafe-inline'", "'unsafe-eval'", "*", "data:", "http:"):
        results.check(f"the CSP does not allow {word}", word in policy, False)

    create_admin()
    admin = app.app.test_client()
    log_in(admin)
    visitor = app.app.test_client()
    responses = {
        "a page": visitor.get("/"),
        "an admin page": admin.get("/admin"),
        "JSON": visitor.get("/api/artworks/1"),
        "a static file": visitor.get("/static/css/style.css"),
        "a 404": visitor.get("/no-such-page"),
        "an API 405": visitor.get("/api/cart"),
        "a redirect": visitor.post("/cart/add", data={"artwork_id": "1"}),
    }
    for label, response in responses.items():
        missing = [name for name, value in app.SECURITY_HEADERS.items()
                   if response.headers.get(name) != value]
        results.check(f"{label} ({response.status_code}): headers missing", missing, [])


class Inline(HTMLParser):
    """Anything in a page that a strict CSP would block."""

    def __init__(self, html):
        super().__init__()
        self.found = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and "src" not in attrs:
            self.found.append("inline <script>")
        if tag == "style":
            self.found.append("<style> element")
        for name, value in attrs.items():
            if name == "style":
                self.found.append(f"style= on <{tag}>")
            if name.startswith("on"):
                self.found.append(f"{name}= on <{tag}>")
            if name in ("href", "src", "action") and (value or "").startswith("javascript:"):
                self.found.append(f"javascript: URL on <{tag}>")


def csp_compatible(results):
    print("  Nothing on any page needs 'unsafe-inline'")
    create_admin()
    admin = app.app.test_client()
    log_in(admin)
    with admin.session_transaction() as session:
        session["cart"] = {"2": 1}
    paths = ["/", "/gallery", "/artists/artist-one", "/artwork/1", "/cart",
             "/checkout", "/orders", "/no-such-page", "/admin", "/admin/orders",
             "/admin/artworks/new", "/admin/artworks/1/edit",
             "/admin/artworks/1/delete"]
    for path in paths:
        found = Inline(get_page(admin, path, results).get_data(as_text=True)).found
        results.check(f"{path}: inline code or style", sorted(set(found)), [])
    found = Inline(app.app.test_client().get("/admin/login").get_data(as_text=True)).found
    results.check("/admin/login: inline code or style", found, [])

    # img-src and font-src are 'self' only, so the stylesheet may not use
    # data: URLs or other sites' files.
    css = (PROJECT_ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+)", css)
    outside = [url for url in urls if re.match(r"(data:|https?:|//)", url)]
    results.check("style.css url()s outside this site", outside, [])


def main():
    results = Results()
    for case in (escaping, escape_hatches, headers, csp_compatible):
        with temp_database():
            case(results)
        print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
