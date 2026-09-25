"""
Is the header built so the phone menu works -- and still works without it?

Run it:

    python tests/test_navigation.py

What the menu LOOKS like is checked in a browser. What is checked here is
the structure that behaviour depends on, which a template edit could break
without anything looking wrong on a wide screen: the button points at the
nav, comes before it, starts closed, and the cart count exists exactly once.
And one CSS rule, because it has already gone wrong once.
"""

import re
import sys

from support import PROJECT_ROOT, Results, place_order, temp_database

import app

# Not /about: it still returns bare text from Stage 1, not a page.
PAGES = ["/", "/gallery", "/artists/artist-one", "/artwork/1", "/cart", "/orders",
         "/no-such-page"]


def header_structure(results):
    print("  The header on every kind of page")
    client, reference = place_order(artwork_id=2)   # a browser with a remembered order
    for path in PAGES + [f"/order/{reference}"]:
        html = client.get(path).get_data(as_text=True)
        header = re.search(r'<header class="site-header">.*?</header>', html, re.S).group(0)
        toggle = re.search(r"<button[^>]*menu-toggle[^>]*>", header)
        ok = (
            toggle is not None
            and 'aria-controls="site-nav"' in toggle.group(0)
            and 'aria-expanded="false"' in toggle.group(0)
            and 'type="button"' in toggle.group(0)
            # the nav it controls exists, and is not hidden by the HTML itself:
            # with JavaScript off, only the CSS decides, and it shows the links
            and re.search(r'<nav class="site-nav" id="site-nav" aria-label="Main">', header)
            # the button comes straight before the nav, so Tab goes into it next
            and header.index("menu-toggle") < header.index('id="site-nav"')
            # the cart is outside the nav, so it stays visible when the menu is shut
            and header.index("cart-link") > header.index("</nav>")
            and html.count('id="cart-count"') == 1
        )
        if ok:
            results.ok(f"{path}: button -> nav, cart outside, one count")
        else:
            results.fail(f"{path}: header structure")

    html = client.get("/cart").get_data(as_text=True)
    results.check("on /cart, the cart link is marked as the current page",
                  bool(re.search(r'class="cart-link"[^>]*aria-current="page"', html)), True)
    results.check("nav.js is loaded", "js/nav.js" in html, True)


def css_contract(results):
    """The bug this pins: a shared rule gave the button display: inline-flex,
    out-ranking .menu-toggle { display: none } -- a dead Menu button with
    JavaScript off. Only two rules may set the button's display."""
    print("  Only the JS-on rule may show the menu button")
    css = (PROJECT_ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # comments may quote rules
    setters = sorted(
        " ".join(selector.split())
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        if re.search(r"(^|;)\s*display\s*:", body)
        for selector in selectors.split(",")
        # the element a selector styles is its LAST part: ".menu-toggle[...] ~
        # .site-nav" mentions the button but styles the nav
        if "menu-toggle" in selector.split()[-1] and ":focus" not in selector)
    results.check("the rules that set .menu-toggle's display", setters,
                  [".menu-toggle", ".site-header--menu .menu-toggle"])


def main():
    results = Results()
    with temp_database():
        header_structure(results)
    print()
    css_contract(results)
    print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
