"""
Are uploaded images checked, cleaned and stored safely?

Run it:

    python tests/test_uploads.py

Every file here is made by the test itself, with Pillow, so each one is known
exactly -- including the hostile ones. Uploads go to a throwaway folder, never
to static/images/artworks.
"""

import io
import os
import re
import sqlite3
import sys
from contextlib import contextmanager

from PIL import Image, ImageCms
from PIL.PngImagePlugin import PngInfo

from support import (Results, create_admin, direct_connection, log_in,
                     temp_database, temp_folder)

import app

GENERATED_NAME = re.compile(r"artworks/[0-9a-f]{32}\.(jpg|png|webp)")


@contextmanager
def temp_uploads():
    """Point the app's upload folder at a throwaway one, and put it back."""
    original = app.UPLOAD_DIR
    with temp_folder() as folder:
        app.UPLOAD_DIR = folder
        try:
            yield folder
        finally:
            app.UPLOAD_DIR = original


def make_image(kind="PNG", size=(40, 30), mode="RGB", **save_options):
    """The bytes of a small image, made here so its contents are known."""
    buffer = io.BytesIO()
    Image.new(mode, size, "white" if mode != "1" else 1).save(buffer, kind, **save_options)
    return buffer.getvalue()


def form(data=None, filename="upload.png", content_type="image/png", **fields):
    """A valid artwork form carrying one uploaded file (or none, if data is None)."""
    values = {
        "artist_id": "1", "title": "Uploaded Work", "medium": "Oil on Canvas",
        "category": "Painting", "description": "Placeholder artwork description.",
        "price": "100", "inventory_quantity": "1", "display_order": "100",
        "image": "",
    }
    values.update(fields)
    if data is not None:
        # The test client sends a (stream, filename, content type) tuple as a
        # multipart file part -- exactly what a browser does.
        values["image_file"] = (io.BytesIO(data), filename, content_type)
    return values


def admin_client():
    create_admin()
    client = app.app.test_client()
    log_in(client)
    return client


def newest_artwork():
    with direct_connection() as connection:
        return connection.execute(
            "SELECT * FROM artworks ORDER BY id DESC LIMIT 1").fetchone()


def count_artworks():
    with direct_connection() as connection:
        return connection.execute("SELECT COUNT(*) FROM artworks").fetchone()[0]


def accepting(results):
    print("  A good upload is stored under a name we chose")
    client = admin_client()
    with temp_uploads() as folder:
        response = client.post("/admin/artworks/new",
                               data=form(make_image("PNG", (40, 30)),
                                         filename="../../evil.php"))
        results.check("a PNG is accepted", response.status_code, 302)

        row = newest_artwork()
        results.check("the stored name is generated, not '../../evil.php'",
                      bool(GENERATED_NAME.fullmatch(row["image"])), True)
        results.check("the stored size is the file's",
                      (row["image_width"], row["image_height"]), (40, 30))
        saved = folder / row["image"].removeprefix("artworks/")
        results.check("the file is in the upload folder", saved.is_file(), True)
        results.check("nothing else was written there", len(list(folder.iterdir())), 1)

        # The extension comes from what the file IS. A PNG that arrives
        # calling itself photo.jpg, image/jpeg, is saved as a .png.
        client.post("/admin/artworks/new",
                    data=form(make_image("PNG"), filename="photo.jpg",
                              content_type="image/jpeg"))
        results.check("a PNG named photo.jpg is saved as .png",
                      newest_artwork()["image"].endswith(".png"), True)

        for kind, suffix in (("JPEG", ".jpg"), ("WEBP", ".webp")):
            client.post("/admin/artworks/new", data=form(make_image(kind)))
            results.check(f"a {kind} is saved as {suffix}",
                          newest_artwork()["image"].endswith(suffix), True)


def cleaning(results):
    print("  What is kept from the original, and what is not")
    client = admin_client()

    def upload_and_read(data, filename="upload.jpg"):
        client.post("/admin/artworks/new", data=form(data, filename=filename))
        name = newest_artwork()["image"].removeprefix("artworks/")
        return (app.UPLOAD_DIR / name).read_bytes()

    with temp_uploads():
        # A phone photo: stored sideways, with "rotate 90" and a GPS position
        # in its EXIF metadata. 0x0112 is Orientation; 0x8825 points to GPS.
        exif = Image.Exif()
        exif[0x0112] = 6
        exif.get_ifd(0x8825)[2] = (51.0, 30.0, 0.0)  # GPSLatitude
        stored = upload_and_read(make_image("JPEG", (60, 20), exif=exif.tobytes()))
        with Image.open(io.BytesIO(stored)) as image:
            results.check("the photo was turned upright (60x20 became 20x60)",
                          image.size, (20, 60))
            results.check("...and the size stored matches",
                          (newest_artwork()["image_width"],
                           newest_artwork()["image_height"]), (20, 60))
            results.check("no EXIF survives: no GPS position, no camera data",
                          len(image.getexif()), 0)

        # A text comment in a PNG.
        info = PngInfo()
        info.add_text("Comment", "private-note-xyz")
        stored = upload_and_read(make_image("PNG", pnginfo=info), "note.png")
        results.check("a PNG's text comment is gone",
                      b"private-note-xyz" in stored, False)

        # A "polyglot": a real JPEG with a script appended after its end.
        # Decoders stop at the end marker, so it still opens as an image.
        hostile = make_image("JPEG") + b"<script>alert('hi')</script>"
        stored = upload_and_read(hostile)
        results.check("bytes hidden after the image are gone",
                      b"<script>" in stored, False)

        # The colour profile is the one thing deliberately kept.
        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        stored = upload_and_read(make_image("JPEG", icc_profile=srgb))
        with Image.open(io.BytesIO(stored)) as image:
            results.check("the colour profile is kept",
                          image.info.get("icc_profile") == srgb, True)

        # A print-shop CMYK JPEG is converted to RGB, which browsers expect.
        stored = upload_and_read(make_image("JPEG", mode="CMYK"))
        with Image.open(io.BytesIO(stored)) as image:
            results.check("a CMYK JPEG is stored as RGB", image.mode, "RGB")

        # A phone's MPO: a JPEG with a second picture inside.
        buffer = io.BytesIO()
        Image.new("RGB", (30, 40)).save(buffer, "MPO", save_all=True,
                                        append_images=[Image.new("RGB", (30, 40))])
        response = client.post("/admin/artworks/new", data=form(buffer.getvalue(),
                                                                filename="phone.jpg"))
        results.check("a phone's MPO JPEG is accepted", response.status_code, 302)
        results.check("...and saved as a plain .jpg",
                      newest_artwork()["image"].endswith(".jpg"), True)


def refusing(results):
    print("  Files that are refused, with nothing written")
    client = admin_client()

    truncated = make_image("JPEG", (200, 200))
    cases = {
        "text calling itself a JPEG": (b"hello, not an image", "photo.jpg"),
        "an SVG (can carry a script)": (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            b'<script>alert(1)</script></svg>', "drawing.svg"),
        "a real GIF (a format we do not accept)": (make_image("GIF"), "anim.gif"),
        "a real BMP (likewise)": (make_image("BMP"), "old.bmp"),
        "half a JPEG": (truncated[: len(truncated) // 2], "cut.jpg"),
        "an empty file": (b"", "empty.png"),
        # A decompression bomb in miniature: 8000 x 8000 is 64 million pixels,
        # over the limit, yet one-bit pixels of one colour compress to a few
        # kilobytes.
        "too many pixels (8000 x 8000)": (make_image("PNG", (8000, 8000), mode="1"),
                                          "bomb.png"),
        "one side too long (20001 x 1)": (make_image("PNG", (20001, 1)), "long.png"),
    }
    with temp_uploads() as folder:
        for description, (data, filename) in cases.items():
            response = client.post("/admin/artworks/new",
                                   data=form(data, filename=filename))
            html = response.get_data(as_text=True)
            results.check(f"{description}: 400", response.status_code, 400)
            results.check("...with the error on the upload field",
                          'id="error-image_file"' in html, True)
        results.check("no artwork was created by any of them", count_artworks(), 6)
        results.check("no file was written by any of them", list(folder.iterdir()), [])

        bomb_page = client.post("/admin/artworks/new",
                                data=form(make_image("PNG", (8000, 8000), mode="1")))
        results.check("the too-many-pixels message gives the size",
                      "8,000 × 8,000 pixels" in bomb_page.get_data(as_text=True), True)


def size_limit(results):
    print("  A request over MAX_CONTENT_LENGTH")
    client = admin_client()
    original = app.app.config["MAX_CONTENT_LENGTH"]
    # Lowered for the test, so it needs a 30 KB file rather than a 20 MB one.
    app.app.config["MAX_CONTENT_LENGTH"] = 10_000
    try:
        noise = Image.frombytes("RGB", (100, 100), os.urandom(30_000))
        buffer = io.BytesIO()
        noise.save(buffer, "PNG")
        with temp_uploads() as folder:
            response = client.post("/admin/artworks/new", data=form(buffer.getvalue()))
            results.check("is refused with 413", response.status_code, 413)
            results.check("...on a page that says why",
                          "too large" in response.get_data(as_text=True), True)
            results.check("...and nothing was written", list(folder.iterdir()), [])
    finally:
        app.app.config["MAX_CONTENT_LENGTH"] = original


def nothing_half_done(results):
    print("  A file never outlives a save that failed")
    client = admin_client()
    with temp_uploads() as folder:
        # 1. The image is fine but the price is not.
        response = client.post("/admin/artworks/new",
                               data=form(make_image(), price="lots"))
        html = response.get_data(as_text=True)
        results.check("a bad price with a good image: 400", response.status_code, 400)
        results.check("...no file written", list(folder.iterdir()), [])
        results.check("...and the form says to choose the file again",
                      "Choose the file again" in html, True)

        # 2. The file is written, then the database refuses the row.
        real_insert = app.insert_artwork

        def failing_insert(record):
            raise sqlite3.OperationalError("database is locked")

        app.insert_artwork = failing_insert
        app.app.logger.disabled = True   # the 500 is expected; keep the output quiet
        try:
            response = client.post("/admin/artworks/new", data=form(make_image()))
        finally:
            app.insert_artwork = real_insert
            app.app.logger.disabled = False
        results.check("a failed INSERT is a 500", response.status_code, 500)
        results.check("...and its file was deleted again", list(folder.iterdir()), [])

        # 3. An edit refused as a conflict (the stock moved) keeps no file.
        edit = form(make_image(), artist_id="2", inventory_quantity="12",
                    loaded_inventory="11", image="placeholders/artwork-02.svg")
        response = client.post("/admin/artworks/2/edit", data=edit)
        html = response.get_data(as_text=True)
        results.check("a stale edit with an upload: 409", response.status_code, 409)
        results.check("...no file kept", list(folder.iterdir()), [])
        results.check("...and the form says to choose the file again",
                      "choose the file again" in html, True)


def editing(results):
    print("  Replacing, keeping, and borrowing images")
    client = admin_client()
    with temp_uploads():
        base = dict(artist_id="2", inventory_quantity="12", loaded_inventory="12",
                    image="placeholders/artwork-02.svg")

        response = client.post("/admin/artworks/2/edit",
                               data=form(make_image("PNG", (50, 70)), **base))
        results.check("replacing the image with an upload", response.status_code, 302)
        with direct_connection() as connection:
            row = connection.execute("SELECT * FROM artworks WHERE id = 2").fetchone()
        uploaded = row["image"]
        results.check("...points the work at the new file",
                      bool(GENERATED_NAME.fullmatch(uploaded)), True)
        results.check("...with the new file's size",
                      (row["image_width"], row["image_height"]), (50, 70))

        page = client.get("/admin/artworks/2/edit").get_data(as_text=True)
        results.check("the edit form now offers the upload as the current choice",
                      f'<option value="{uploaded}" selected>' in page, True)
        results.check("...and shows it", f'images/{uploaded}"' in page, True)

        keep = dict(base, image=uploaded)
        response = client.post("/admin/artworks/2/edit", data=form(**keep))
        results.check("saving without a new file keeps it", response.status_code, 302)

        # Work 3 cannot point at work 2's upload: it is not on work 3's menu.
        borrow = form(image=uploaded, inventory_quantity="0", loaded_inventory="0")
        response = client.post("/admin/artworks/3/edit", data=borrow)
        results.check("another work cannot borrow that upload", response.status_code, 400)


def main():
    results = Results()
    for case in (accepting, cleaning, refusing, size_limit, nothing_half_done,
                 editing):
        with temp_database():
            case(results)
        print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
