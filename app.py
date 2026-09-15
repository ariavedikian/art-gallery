"""
Art Gallery — a Flask web application.

Stage 3: the homepage becomes a gallery landing page.

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

# image_width / image_height are the image's real pixel dimensions. The browser
# uses them to reserve the right amount of space before the file has loaded.
ARTWORKS = [
    {
        "id": 1,
        "title": "Artwork Title",
        "artist_name": "Artist One",
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
        "title": "Artwork Title",
        "artist_name": "Artist Two",
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
        "title": "Artwork Title",
        "artist_name": "Artist One",
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
        "title": "Artwork Title",
        "artist_name": "Artist Two",
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
        "title": "Artwork Title",
        "artist_name": "Artist One",
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
        "title": "Artwork Title",
        "artist_name": "Artist Two",
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
    # Python decides WHAT to show. The template only decides how it looks.
    # At Stage 6 this list comprehension becomes: WHERE is_featured = 1
    featured = [art for art in ARTWORKS if art["is_featured"]]

    # The first featured work gets the large spotlight; the rest fill the grid.
    # Guard against an empty list: featured[0] on [] would raise IndexError
    # and turn the whole homepage into a 500 error.
    spotlight = featured[0] if featured else None

    return render_template(
        "index.html",
        gallery_name=GALLERY_NAME,
        artists=ARTISTS,
        spotlight=spotlight,
        featured=featured[1:],
    )


@app.route("/about")
def about():
    return "Placeholder gallery description."


@app.route("/health")
def health():
    return {"status": "ok", "stage": 3}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
