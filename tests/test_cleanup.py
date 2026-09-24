"""
Are an image's files deleted when nothing uses them -- and only then?

Run it:

    python tests/test_cleanup.py

Deleting is the one thing in Stage 17 that cannot be undone, so most of this
file is about what must NOT be deleted: a placeholder, a file another row
still uses, the files of a save that failed, a file the sweep cannot be sure
about.
"""

import os
import pathlib
import sys
import time

from support import (PROJECT_ROOT, Results, direct_connection, place_order,
                     temp_database)
from test_uploads import admin_client, form, gradient, newest_artwork, temp_uploads

import app

# Work 2 as the edit form sends it back, image and stock unchanged.
WORK_2 = dict(artist_id="2", inventory_quantity="12", loaded_inventory="12")


def files_in(folder):
    return sorted(path.name for path in folder.iterdir())


def stem(stored):
    return stored.removeprefix("artworks/").rsplit(".", 1)[0]


def image_of(artwork_id):
    with direct_connection() as connection:
        return connection.execute("SELECT image FROM artworks WHERE id = ?",
                                  (artwork_id,)).fetchone()["image"]


def upload_to_work_2(client, current):
    """Replace work 2's image with a fresh 1200px upload (original + 2 renditions)."""
    response = client.post("/admin/artworks/2/edit",
                           data=form(gradient((1200, 900)), image=current, **WORK_2))
    assert response.status_code == 302, response.status_code
    return image_of(2)


def replacing(results):
    print("  Replacing an image deletes the old one's files")
    client = admin_client()
    with temp_uploads() as folder:
        first = upload_to_work_2(client, "placeholders/artwork-02.svg")
        results.check("the first upload: an original and two renditions",
                      len(files_in(folder)), 3)
        results.check("...and the placeholder it replaced is still on disk",
                      (PROJECT_ROOT / "static/images/placeholders/artwork-02.svg").is_file(),
                      True)

        # A rendition at a width RENDITION_WIDTHS no longer lists, as if the
        # widths had changed since this image was uploaded. It belongs to the
        # image all the same.
        (folder / f"{stem(first)}-300.webp").write_bytes(b"old width")

        second = upload_to_work_2(client, first)
        results.check("after replacing it, only the new image's files remain",
                      all(name.startswith(stem(second)) for name in files_in(folder)), True)
        results.check("...three of them (the old-width rendition went too)",
                      len(files_in(folder)), 3)

        response = client.post("/admin/artworks/2/edit",
                               data=form(image=second, **WORK_2))
        results.check("saving without changing the image", response.status_code, 302)
        results.check("...deletes nothing", len(files_in(folder)), 3)

        response = client.post("/admin/artworks/2/edit",
                               data=form(image="placeholders/artwork-02.svg", **WORK_2))
        results.check("switching back to a placeholder", response.status_code, 302)
        results.check("...deletes the upload's files", files_in(folder), [])


def failed_saves_delete_nothing(results):
    print("  A save that did not happen deletes nothing")
    client = admin_client()
    with temp_uploads() as folder:
        current = upload_to_work_2(client, "placeholders/artwork-02.svg")
        before = files_in(folder)

        stale = dict(WORK_2, loaded_inventory="11")   # the stock "moved"
        response = client.post("/admin/artworks/2/edit",
                               data=form(gradient((1200, 900)), image=current, **stale))
        results.check("a replacement refused as a conflict (409)", response.status_code, 409)
        results.check("...keeps the current image's files, and adds none",
                      files_in(folder), before)

        response = client.post("/admin/artworks/2/edit",
                               data=form(image="placeholders/artwork-02.svg",
                                         **dict(WORK_2, price="lots")))
        results.check("a switch to a placeholder refused for a bad price (400)",
                      response.status_code, 400)
        results.check("...deletes nothing", files_in(folder), before)


def still_in_use(results):
    print("  A file another row still uses is kept")
    client = admin_client()
    with temp_uploads() as folder:
        shared = upload_to_work_2(client, "placeholders/artwork-02.svg")
        # The form never lets two works share an upload. Force it in the
        # database, as a future feature (or a hand edit) might.
        with direct_connection() as connection:
            connection.execute("UPDATE artworks SET image = ? WHERE id = 6", (shared,))
            connection.commit()

        client.post("/admin/artworks/2/edit",
                    data=form(image="placeholders/artwork-02.svg", **WORK_2))
        results.check("work 2 let go of it, but work 6 still uses it: kept",
                      len(files_in(folder)), 3)


def deleting(results):
    print("  Deleting a work deletes its files -- unless the delete is refused")
    client = admin_client()
    with temp_uploads() as folder:
        client.post("/admin/artworks/new", data=form(gradient((1200, 900))))
        work = newest_artwork()["id"]
        results.check("a new work with an upload: three files", len(files_in(folder)), 3)

        response = client.post(f"/admin/artworks/{work}/delete")
        results.check("deleting it redirects", response.status_code, 302)
        results.check("...and its files are gone", files_in(folder), [])

        # Ticked "Offered for sale" -- form() leaves it unticked -- so it can be bought.
        client.post("/admin/artworks/new",
                    data=form(gradient((1200, 900)), available_for_purchase="1"))
        sold = newest_artwork()["id"]
        place_order(sold)
        client.post(f"/admin/artworks/{sold}/delete")
        results.check("a SOLD work's delete is refused, so its files stay",
                      len(files_in(folder)), 3)


def undeletable_file(results):
    print("  A file that will not delete does not fail the save")
    client = admin_client()
    with temp_uploads() as folder:
        current = upload_to_work_2(client, "placeholders/artwork-02.svg")

        # As on Windows when another program has the file open.
        real_unlink = pathlib.Path.unlink

        def refuse(self, missing_ok=False):
            raise PermissionError(13, "The file is in use", str(self))

        pathlib.Path.unlink = refuse
        app.app.logger.disabled = True
        try:
            response = client.post("/admin/artworks/2/edit",
                                   data=form(image="placeholders/artwork-02.svg", **WORK_2))
        finally:
            pathlib.Path.unlink = real_unlink
            app.app.logger.disabled = False
        results.check("the save still succeeds", response.status_code, 302)
        results.check("...the work now shows the placeholder",
                      image_of(2), "placeholders/artwork-02.svg")
        results.check("...and the files wait for the sweep",
                      all(name.startswith(stem(current)) for name in files_in(folder)), True)


def image_guard(results):
    """Two saves at once, replayed in order: B reads the row, A replaces the
    image (deleting the old files), then B writes. Without the guard, B puts
    the old image name back -- pointing the work at files that are gone."""
    print("  The image is guarded against a save that read it too early")
    client = admin_client()
    with temp_uploads():
        old = upload_to_work_2(client, "placeholders/artwork-02.svg")

        real_validate = app.validate_artwork

        def validate_then_someone_else_saves(form_data, files, current_image=None):
            outcome = real_validate(form_data, files, current_image)
            # Admin A's save lands here: after B's request read the row,
            # before B's UPDATE.
            with direct_connection() as connection:
                connection.execute("UPDATE artworks SET image = "
                                   "'placeholders/artwork-03.svg' WHERE id = 2")
                connection.commit()
            return outcome

        app.validate_artwork = validate_then_someone_else_saves
        try:
            response = client.post("/admin/artworks/2/edit",
                                   data=form(image=old, **dict(WORK_2, title="B's title")))
        finally:
            app.validate_artwork = real_validate
        html = response.get_data(as_text=True)

        results.check("B's save is refused as a conflict (409)", response.status_code, 409)
        results.check("...A's image stands; B did not write the old one back",
                      image_of(2), "placeholders/artwork-03.svg")
        results.check("...the form says the image changed",
                      "image was changed by someone else" in html, True)
        results.check("...and keeps B's title for the retry", "B&#39;s title" in html, True)


def sweeping(results):
    print("  flask sweep-uploads")
    client = admin_client()
    runner = app.app.test_cli_runner()
    with temp_uploads() as folder:
        used = upload_to_work_2(client, "placeholders/artwork-02.svg")
        hour_and_a_bit = time.time() - 2 * 60 * 60

        old_stray = folder / ("b" * 32 + ".jpg")
        old_rendition = folder / ("b" * 32 + "-480.webp")
        new_stray = folder / ("c" * 32 + ".png")
        foreign = folder / "notes.txt"
        for path in (old_stray, old_rendition, new_stray, foreign):
            path.write_bytes(b"x")
        for path in (old_stray, old_rendition, foreign):
            os.utime(path, (hour_and_a_bit, hour_and_a_bit))
        # The work's own files, made old too, so only "in use" protects them.
        for path in folder.glob(f"{stem(used)}*"):
            os.utime(path, (hour_and_a_bit, hour_and_a_bit))

        looked = runner.invoke(args=["sweep-uploads"]).output
        results.check("without --delete it lists the old strays",
                      ("stray: " + old_stray.name in looked,
                       "stray: " + old_rendition.name in looked), (True, True))
        results.check("...and deletes nothing", len(files_in(folder)), 7)
        results.check("...names the recent file it will not touch",
                      "too recent to be sure): " + new_stray.name in looked, True)
        results.check("...and the file whose name we would never write",
                      "not a name this site writes): notes.txt" in looked, True)

        runner.invoke(args=["sweep-uploads", "--delete"])
        left = files_in(folder)
        results.check("--delete removes the old strays",
                      (old_stray.name in left, old_rendition.name in left), (False, False))
        results.check("...keeps the recent one and the foreign one",
                      (new_stray.name in left, "notes.txt" in left), (True, True))
        results.check("...and every file the work uses",
                      len([n for n in left if n.startswith(stem(used))]), 3)

        again = runner.invoke(args=["sweep-uploads"]).output
        results.check("a second run finds nothing", "No stray files." in again, True)


def main():
    results = Results()
    for case in (replacing, failed_saves_delete_nothing, still_in_use, deleting,
                 undeletable_file, image_guard, sweeping):
        with temp_database():
            case(results)
        print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
