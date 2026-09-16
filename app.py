"""
Art Gallery — a Flask web application.

Stage 4: artist pages, served by one dynamic route.

The placeholder data below lives in this file *temporarily*. At Stage 5 it moves
into SQLite. Routes never read the lists directly: they call the data-access
functions further down, so at Stage 6 only those function bodies change.
"""

from flask import Flask, abort, render_template

app = Flask(__name__)


# --- Placeholder content (replaced by the database at Stage 5) ----------------
# Nothing here is real. Real Jansem and Carzou material arrives at Stage 21.

GALLERY_NAME = "Gallery Placeholder"

ARTISTS = [
    {
        "slug": "artist-one",
        "name": "Artist One",
        "lifespan": "1900–1980",
        "summary": "Placeholder artist description. One or two sentences "
                   "introducing the artist and the character of their work.",
        "bio": "Placeholder biography paragraph. A longer passage about the "
               "artist, used on their collection page. Replaced with verified "
               "material at Stage 21.",
        "portrait": "placeholders/artist-one.svg",
    },
    {
        "slug": "artist-two",
        "name": "Artist Two",
        "lifespan": "1905–1985",
        "summary": "Placeholder artist description. One or two sentences "
                   "introducing the artist and the character of their work.",
        "bio": "Placeholder biography paragraph. A longer passage about the "
               "artist, used on their collection page. Replaced with verified "
               "material at Stage 21.",
        "portrait": "placeholders/artist-two.svg",
    },
]

# Each artwork points at its artist by `artist_slug`, not by copying the name.
# If an artist is renamed, it changes in one place. In the database this
# becomes a foreign key (Stage 5).
# image_width / image_height let the browser reserve space before the image loads.
ARTWORKS = [
    {
        "id": 1,
        "artist_slug": "artist-one",
        "title": "Artwork Title",
        "year": "2025",
        "medium": "Oil on Canvas",
        "price_cents": 480000,
        "available": True,
        "is_featured": True,
        "image": "placeholders/artwork-01.svg",
        "image_width": 900,
        "image_height": 1100,
    },
    {
        "id": 2,
        "artist_slug": "artist-two",
        "title": "Artwork Title",
        "year": "2025",
        "medium": "Lithograph",
        "price_cents": 125000,
        "available": True,
        "is_featured": True,
        "image": "placeholders/artwork-02.svg",
        "image_width": 1000,
        "image_height": 800,
    },
    {
        "id": 3,
        "artist_slug": "artist-one",
        "title": "Artwork Title",
        "year": "2025",
        "medium": "Ink on Paper",
        "price_cents": 96000,
        "available": False,
        "is_featured": True,
        "image": "placeholders/artwork-03.svg",
        "image_width": 850,
        "image_height": 1050,
    },
    {
        "id": 4,
        "artist_slug": "artist-two",
        "title": "Artwork Title",
        "year": "2025",
        "medium": "Gouache on Paper",
        "price_cents": 210000,
        "available": True,
        "is_featured": True,
        "image": "placeholders/artwork-04.svg",
        "image_width": 700,
        "image_height": 1200,
    },
    {
        "id": 5,
        "artist_slug": "artist-one",
        "title": "Artwork Title",
        "year": "2025",
        "medium": "Oil on Canvas",
        "price_cents": 640000,
        "available": True,
        "is_featured": True,
        "image": "placeholders/artwork-05.svg",
        "image_width": 1300,
        "image_height": 800,
    },
    {
        "id": 6,
        "artist_slug": "artist-two",
        "title": "Artwork Title",
        "year": "2025",
        "medium": "Etching",
        "price_cents": 58000,
        "available": True,
        "is_featured": False,
        "image": "placeholders/artwork-06.svg",
        "image_width": 1000,
        "image_height": 1000,
    },
]


# --- Data access -------------------------------------------------------------
# The only code that knows the data lives in Python lists. At Stage 6 these
# bodies become SQL queries; nothing that calls them has to change.

def get_artists():
    return ARTISTS


def get_artist(slug):
    """Return the artist with this slug, or None if there is no such artist."""
    for artist in ARTISTS:
        if artist["slug"] == slug:
            return artist
    return None


def _with_artist_name(art):
    """Return a copy of an artwork with its artist's name added.

    This is a JOIN written by hand: look up the related artist and combine the
    two records. At Stage 6 one line of SQL does this. We build a new dict
    with {**art, ...} instead of editing `art`, because ARTWORKS is shared by
    every request the server handles; changing it would leak between visitors.
    """
    artist = get_artist(art["artist_slug"])
    return {**art, "artist_name": artist["name"]}


def get_featured_artworks():
    return [_with_artist_name(art) for art in ARTWORKS if art["is_featured"]]


def get_artworks_by_artist(slug):
    return [_with_artist_name(art) for art in ARTWORKS if art["artist_slug"] == slug]


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
    dict into that template's variables. Without it, every route would have
    to remember to pass the nav data, and the first one that forgot would
    render a broken header.
    """
    return {
        "gallery_name": GALLERY_NAME,
        "nav_artists": get_artists(),
    }


# --- Routes ------------------------------------------------------------------

@app.route("/")
def home():
    # Python decides WHAT to show. The template only decides how it looks.
    featured = get_featured_artworks()

    # Guard against an empty list: featured[0] on [] would raise IndexError
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
    # types. An unknown slug is the visitor's mistake, not a server crash:
    # abort(404) stops here and sends a 404 Not Found response.
    if artist is None:
        abort(404)

    return render_template(
        "artist.html",
        artist=artist,
        artworks=get_artworks_by_artist(slug),
    )


@app.route("/about")
def about():
    return "Placeholder gallery description."


@app.route("/health")
def health():
    return {"status": "ok", "stage": 4}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
