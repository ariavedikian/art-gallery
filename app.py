"""
Art Gallery — a Flask web application.

Stage 2: the homepage, rendered from HTML templates.

The placeholder data below lives in this file *temporarily*. At Stage 5 it moves
into SQLite and this file will query the database instead. The shape of each
dictionary deliberately matches the table columns we will create, so that move
is a swap rather than a rewrite.
"""

from flask import Flask, render_template

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
        "portrait": "placeholders/artist-one.svg",
    },
    {
        "slug": "artist-two",
        "name": "Artist Two",
        "lifespan": "1905–1985",
        "summary": "Placeholder artist description. One or two sentences "
                   "introducing the artist and the character of their work.",
        "portrait": "placeholders/artist-two.svg",
    },
]

FEATURED_ARTWORKS = [
    {
        "id": 1,
        "title": "Artwork Title",
        "artist_name": "Artist One",
        "year": "2025",
        "medium": "Oil on Canvas",
        "price_cents": 480000,
        "available": True,
        "image": "placeholders/artwork-01.svg",
    },
    {
        "id": 2,
        "title": "Artwork Title",
        "artist_name": "Artist Two",
        "year": "2025",
        "medium": "Lithograph",
        "price_cents": 125000,
        "available": True,
        "image": "placeholders/artwork-02.svg",
    },
    {
        "id": 3,
        "title": "Artwork Title",
        "artist_name": "Artist One",
        "year": "2025",
        "medium": "Ink on Paper",
        "price_cents": 96000,
        "available": False,
        "image": "placeholders/artwork-03.svg",
    },
]


# --- Template helpers --------------------------------------------------------

@app.template_filter("usd")
def usd(cents):
    """Turn 480000 into "$4,800". Money is stored as whole cents (an integer)
    because floats lose precision: 0.1 + 0.2 != 0.3 in binary arithmetic.
    Formatting is presentation, so it belongs here rather than in the data."""
    return "${:,.0f}".format(cents / 100)


# --- Routes ------------------------------------------------------------------

@app.route("/")
def home():
    # render_template finds the file in templates/, fills in the values we pass
    # as keyword arguments, and returns the finished HTML as the response.
    return render_template(
        "index.html",
        gallery_name=GALLERY_NAME,
        artists=ARTISTS,
        featured=FEATURED_ARTWORKS,
    )


@app.route("/about")
def about():
    return "Placeholder gallery description."


@app.route("/health")
def health():
    return {"status": "ok", "stage": 2}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
