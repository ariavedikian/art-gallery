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
DROP TABLE IF EXISTS admins;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
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
    image_height  INTEGER NOT NULL,   -- reserve space before the file loads

    -- Curated ordering: lower numbers appear first, and the lowest-numbered
    -- featured work becomes the homepage spotlight. Without this, the gallery
    -- would be stuck with whatever order the rows happened to be inserted in.
    --
    -- Seed values step by 10 rather than 1, so a work can be slipped between
    -- two others (15, say) without renumbering the whole collection.
    display_order INTEGER NOT NULL DEFAULT 100
);


-- An index is a lookup shortcut the database maintains for you: without one,
-- finding every artwork by an artist means reading every row in the table.
-- Indexes cost a little space and make writes slightly slower, so you add them
-- for columns you actually search on. artist_id is looked up on every
-- artist page, so it earns one.
CREATE INDEX idx_artworks_artist_id ON artworks (artist_id);


-- --- orders ------------------------------------------------------------------
-- One row per completed purchase. Written only inside a transaction, by
-- place_order() in app.py, and never updated afterwards by the checkout flow:
-- an order is a record of something that happened.
CREATE TABLE orders (
    id         INTEGER PRIMARY KEY,

    -- The public identifier, used in the confirmation URL.
    --
    -- NOT the id. Ids are sequential, so /order/3 invites anyone to try
    -- /order/2 and read a stranger's name, email and address. A random
    -- reference is not a password — it is the only thing standing between a
    -- curious visitor and someone else's order, so it has to be long enough
    -- that guessing is hopeless. Generated with secrets.token_urlsafe.
    reference  TEXT NOT NULL UNIQUE,

    -- Who bought it and where it goes. Deliberately plain text: this is a
    -- shipping address, not a structured postal database, and pretending
    -- otherwise breaks the moment someone outside your assumed country buys
    -- something.
    customer_name    TEXT NOT NULL,
    customer_email   TEXT NOT NULL,
    shipping_address TEXT NOT NULL,

    -- The total as it was charged. Recomputing it later from order_items
    -- would give the same answer today and possibly a different one after a
    -- refund, a correction or a rounding-rule change. Store what happened.
    subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),

    -- 'mock' until Stage 14 introduces Stripe. Named rather than assumed, so
    -- a real payment and a fake one can never be confused in the data.
    payment_method TEXT NOT NULL,

    -- The statuses an order may have. The CHECK means the database refuses
    -- anything outside this list, so a typo is an error at the moment of
    -- writing rather than a value nobody's code handles.
    --
    --   pending    created, payment not yet confirmed (Stage 14 uses this,
    --              because a Stripe payment is confirmed asynchronously)
    --   paid       what the mock payment produces today
    --   shipped    dispatched
    --   cancelled  did not complete, or was withdrawn
    --
    -- Which TRANSITIONS are legal is not written anywhere yet, deliberately:
    -- nothing in the app can change a status. Those rules arrive with the
    -- things that can -- the webhook at Stage 14, the admin at Stage 16.
    status     TEXT NOT NULL DEFAULT 'paid'
               CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),

    -- SQLite has no DATE type, so an ISO 8601 string in UTC. It sorts
    -- correctly as text, which is exactly why that format was chosen.
    placed_at  TEXT NOT NULL
);


-- --- order_items -------------------------------------------------------------
-- The lines of an order: what was bought, how many, and at what price.
CREATE TABLE order_items (
    id       INTEGER PRIMARY KEY,

    -- ON DELETE CASCADE: deleting an order deletes its lines. Unlike an
    -- artist, an order's lines have no meaning without the order, so there is
    -- nothing to protect by refusing.
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,

    -- ON DELETE RESTRICT: refuse to delete an artwork that has been sold.
    -- A sale is a fact about the past and must not be quietly erased.
    artwork_id INTEGER NOT NULL REFERENCES artworks(id) ON DELETE RESTRICT,

    -- A SNAPSHOT, not a live reference.
    --
    -- The artwork_id above says WHICH work was bought. These columns say what
    -- it cost and what it was called AT THAT MOMENT. Without them, raising a
    -- price next year would silently rewrite every receipt ever issued, and a
    -- retitled work would make an old order describe something the buyer
    -- never saw.
    --
    -- The rule: a record of the past stores values, not pointers to a present
    -- that keeps moving. Stage 13 comes back to this.
    title_at_purchase  TEXT NOT NULL,
    artist_at_purchase TEXT NOT NULL,
    unit_price_cents   INTEGER NOT NULL CHECK (unit_price_cents >= 0),

    quantity INTEGER NOT NULL CHECK (quantity > 0)
);


-- Every confirmation page looks an order up by reference, and every order page
-- then fetches its lines by order_id. Both earn an index. (reference already
-- has one: UNIQUE creates an index to enforce itself.)
CREATE INDEX idx_order_items_order_id ON order_items (order_id);

-- The orders list is read newest first. ISO 8601 text sorts chronologically,
-- which is exactly why that format was chosen for placed_at.
CREATE INDEX idx_orders_placed_at ON orders (placed_at DESC);


-- --- admins ------------------------------------------------------------------
-- The people who can use /admin. Deliberately EMPTY after a rebuild: seed.sql
-- never creates one, because a password in a committed file is a password
-- everyone with the repository knows. Create one from your own terminal:
--
--     flask --app app create-admin yourname
--
-- which asks for the password without echoing it.
CREATE TABLE admins (
    id            INTEGER PRIMARY KEY,

    -- COLLATE NOCASE makes UNIQUE and every comparison ignore case, so
    -- "Ari" and "ari" cannot be two different admins, and logging in as
    -- either finds the same row.
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,

    -- NOT the password. A salted, deliberately slow one-way hash of it, made
    -- by Werkzeug's generate_password_hash. The text starts with the method
    -- used ("scrypt:..."), so a stronger method can be adopted later without
    -- breaking the hashes already stored.
    password_hash TEXT NOT NULL,

    created_at    TEXT NOT NULL
);
