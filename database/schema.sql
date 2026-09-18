-- =============================================================================
-- Art Gallery — database schema
--
-- Build the database with:  python init_db.py --reset
--
-- This file describes the SHAPE of the data: which tables exist, what columns
-- they hold, and the rules the database itself enforces. The data lives
-- separately, in seed.sql. Keeping them apart means the same structure can be
-- filled with placeholder content now and real content later.
--
-- Everything here is placeholder-friendly: no artist or artwork names appear
-- in this file at all.
-- =============================================================================


-- SQLite does not enforce foreign keys unless asked, on every connection.
-- Leaving this off is a classic source of quietly broken data.
PRAGMA foreign_keys = ON;


-- Drop in reverse order of dependency: artworks points at artists, so it has
-- to go first. Dropping artists while artworks still referenced it would be
-- exactly the orphaned-reference problem these tables exist to prevent.
DROP TABLE IF EXISTS artworks;
DROP TABLE IF EXISTS artists;


-- --- artists -----------------------------------------------------------------
CREATE TABLE artists (
    -- INTEGER PRIMARY KEY is special in SQLite: leave it out of an INSERT and
    -- the database fills it in (1, 2, 3, ...). This number identifies the row
    -- forever and never changes, which is exactly why other tables point at it.
    id        INTEGER PRIMARY KEY,

    -- The name used in URLs: /artists/artist-one
    -- UNIQUE means the database refuses a second artist with the same slug.
    -- A slug can be edited freely, because artworks reference id, not slug.
    slug      TEXT NOT NULL UNIQUE,

    name      TEXT NOT NULL,

    -- No NOT NULL: a record without dates is allowed. NULL means "unknown",
    -- which is different from an empty string meaning "deliberately blank".
    lifespan  TEXT,

    summary   TEXT NOT NULL,
    bio       TEXT NOT NULL,
    portrait  TEXT NOT NULL      -- path under static/images/
);


-- --- artworks ----------------------------------------------------------------
CREATE TABLE artworks (
    id            INTEGER PRIMARY KEY,

    -- The foreign key. This value must match an existing artists.id, and the
    -- database refuses any INSERT or UPDATE that would break that.
    --
    -- ON DELETE RESTRICT: refuse to delete an artist who still has artworks.
    -- The alternative, ON DELETE CASCADE, would delete their artworks too.
    -- RESTRICT is the safer default: deleting an artist should be a decision,
    -- not an accident.
    artist_id     INTEGER NOT NULL REFERENCES artists(id) ON DELETE RESTRICT,

    title         TEXT NOT NULL,

    -- TEXT, not INTEGER. Art dates are often approximate ("c. 1955") or a
    -- range ("1962-63"). Store what is true rather than what is tidy.
    year          TEXT,

    medium        TEXT NOT NULL,      -- "Oil on Canvas", "Lithograph", ...
    category      TEXT NOT NULL,      -- broader grouping, used for filtering
    description   TEXT NOT NULL,

    -- Whole cents, never a decimal: 0.1 + 0.2 is not 0.3 in binary floats.
    -- CHECK is a rule the database enforces; a negative price is rejected.
    price_cents   INTEGER NOT NULL CHECK (price_cents >= 0),

    -- Two separate facts, deliberately not merged into one "available" flag:
    --
    --   available_for_purchase  Is this piece offered for sale at all?
    --                           0 for display-only, loaned or not-for-sale work.
    --   inventory_quantity      How many are left? 1 for a unique original,
    --                           30 for an edition of prints, 0 when sold out.
    --
    -- "Sold" on the website is a CONCLUSION drawn from these two
    -- (for sale, but none left), not a fact stored on its own. Storing a
    -- conclusion invites the day it disagrees with the facts behind it.
    available_for_purchase INTEGER NOT NULL DEFAULT 1
                           CHECK (available_for_purchase IN (0, 1)),
    inventory_quantity     INTEGER NOT NULL DEFAULT 1
                           CHECK (inventory_quantity >= 0),

    -- SQLite has no BOOLEAN type. 0 and 1 stand in for false and true.
    is_featured   INTEGER NOT NULL DEFAULT 0 CHECK (is_featured IN (0, 1)),

    image         TEXT NOT NULL,      -- path under static/images/
    image_width   INTEGER NOT NULL,   -- real pixel size, so the browser can
    image_height  INTEGER NOT NULL    -- reserve space before the file loads
);


-- An index is a lookup shortcut the database maintains for you: without one,
-- finding every artwork by an artist means reading every row in the table.
-- Indexes cost a little space and make writes slightly slower, so you add them
-- for columns you actually search on. artist_id is looked up on every
-- artist page, so it earns one.
CREATE INDEX idx_artworks_artist_id ON artworks (artist_id);
