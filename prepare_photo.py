"""
Turn one photo of a work into the files the site serves.

    python prepare_photo.py artworks/carzou/Aurora.jpg aurora

Writes static/images/works/aurora.jpg and its smaller copies, then prints
what the work's row in database/seed.sql needs. The photo goes through the
same code as an admin upload, so it is re-encoded from its pixels and the
camera's metadata (GPS position, serial number) is left behind.

A name is used once: to replace a photo, delete its files and run this again.
"""

import re
import sys
import types
from pathlib import Path

import app

NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def prepare(photo, name):
    if not NAME.fullmatch(name):
        sys.exit("The name must be lowercase letters, digits and hyphens: la-reine-masquee")

    with open(photo, "rb") as file:
        upload, problem = app.prepare_upload(types.SimpleNamespace(stream=file))
    if problem:
        sys.exit(problem)

    stored = f"works/{name}{upload['suffix']}"
    files = {stored: upload["data"]}
    files.update({app.rendition_path(stored, width): data
                  for width, data in upload["renditions"].items()})

    folder = Path(app.app.static_folder) / "images"
    (folder / "works").mkdir(exist_ok=True)
    for path, data in files.items():
        # "x": refuse to overwrite, so a mistyped name cannot replace a photo.
        with open(folder / path, "xb") as target:
            target.write(data)

    width, height = upload["size"]
    print(f"Wrote {len(files)} files. In seed.sql: '{stored}', {width}, {height}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    prepare(sys.argv[1], sys.argv[2])
