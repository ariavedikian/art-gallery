"""
Build the SQLite database from database/schema.sql and database/seed.sql.

    python init_db.py           create the database if it does not exist yet
    python init_db.py --reset   delete it and rebuild it from scratch

Keeping this in a script rather than typing SQL by hand means the database can
be thrown away and rebuilt identically at any time. That is why the .db file
itself is gitignored: it is generated, not source. schema.sql and seed.sql are
the source, and they are what git tracks.
"""

import sqlite3
import sys
from pathlib import Path

# Paths relative to this file, so the script works from any directory.
BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DB_PATH = DATABASE_DIR / "art_gallery.db"
SCHEMA_PATH = DATABASE_DIR / "schema.sql"
SEED_PATH = DATABASE_DIR / "seed.sql"


def build(reset=False):
    if DB_PATH.exists():
        if not reset:
            print(f"{DB_PATH} already exists.")
            print("Run 'python init_db.py --reset' to rebuild it. That DELETES all data.")
            return
        DB_PATH.unlink()
        print("Removed the existing database.")

    # connect() creates the file if it is missing. A connection is an open
    # conversation with the database; everything happens through one.
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON")

        # executescript runs a whole file of statements, unlike execute(),
        # which runs exactly one. It is the right tool here and the wrong tool
        # for user input, which always goes through parameterised queries.
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.executescript(SEED_PATH.read_text(encoding="utf-8"))

        # Nothing is saved until commit(). Until then the changes exist only
        # inside this transaction, and closing without committing throws
        # them away.
        connection.commit()

        artists = connection.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
        artworks = connection.execute("SELECT COUNT(*) FROM artworks").fetchone()[0]
        sources = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

        # orders and order_items are created empty. Counting them here is a
        # cheap way to prove the tables exist after a rebuild.
        orders = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        admins = connection.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        # Always close, even if something above raised an error.
        connection.close()

    print(f"Created {DB_PATH} (schema version {version})")
    print(f"  {artists} artists, {artworks} artworks, {sources} sources")
    print(f"  {orders} orders")
    print(f"  {admins} admins")

    # A rebuild always empties the admins table, since seed.sql never holds a
    # password. Say what to do about it rather than leave a locked admin page
    # to be discovered later.
    if admins == 0:
        print("  To use /admin, create an admin: flask --app app create-admin <name>")


if __name__ == "__main__":
    build(reset="--reset" in sys.argv)
