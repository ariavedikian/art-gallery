"""
Do the stylesheet's small-screen rules still hold?

Run it:

    python tests/test_layout.py

Layout is checked in a browser, at every width, during the stage that
changes it. What is checked HERE is the handful of one-line rules whose
purpose is invisible when you read them -- the kind a tidy-up deletes as
dead code, putting back a bug that only shows on a phone:

- position: relative on the admin table's scroll box
- min-inline-size: 0 on the admin form's fieldsets

plus two rules for the whole stylesheet: no text smaller than 11px, and
breakpoints in em, never px.
"""

import re
import sys

from support import PROJECT_ROOT, Results

STYLESHEET = PROJECT_ROOT / "static" / "css" / "style.css"

# 0.6875rem is 11px at the default text size: the smallest on the site.
SMALLEST_FONT_REM = 0.6875


def rules():
    """[(selector, {property: value})] for every rule, comments removed.

    A deliberately small parser: good enough for this stylesheet, which has
    no nested blocks other than @media, and those are unwrapped by matching
    only the innermost { ... }.
    """
    css = re.sub(r"/\*.*?\*/", "", STYLESHEET.read_text(encoding="utf-8"), flags=re.S)
    found = []
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        declarations = dict(
            (name.strip(), value.strip())
            for name, _, value in (d.partition(":") for d in body.split(";") if ":" in d))
        for selector in selectors.split(","):
            found.append((" ".join(selector.split()), declarations))
    return found, css


def declared(all_rules, selector):
    """Every property set for exactly this selector, across all its rules."""
    merged = {}
    for name, declarations in all_rules:
        if name == selector:
            merged.update(declarations)
    return merged


def main():
    results = Results()
    all_rules, css = rules()

    print("  Rules that only matter on a small screen")
    wrap = declared(all_rules, ".admin-table-wrap")
    results.check(".admin-table-wrap scrolls sideways", wrap.get("overflow-x"), "auto")
    results.check(".admin-table-wrap is positioned, so the visually-hidden "
                  "labels inside cannot escape it", wrap.get("position"), "relative")
    results.check(".admin-form__group can shrink below its widest content",
                  declared(all_rules, ".admin-form__group").get("min-inline-size"), "0")
    print()

    print("  Rules for the whole stylesheet")
    too_small = sorted({
        f"{selector}: {declarations['font-size']}"
        for selector, declarations in all_rules
        if (size := re.fullmatch(r"([\d.]+)rem", declarations.get("font-size", "")))
        and float(size[1]) < SMALLEST_FONT_REM})
    results.check("no font-size below 0.6875rem (11px)", too_small, [])

    px_breakpoints = re.findall(r"@media[^{]*\d+px[^{]*", css)
    results.check("no breakpoint written in px", px_breakpoints, [])

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
