-- =============================================================================
-- Art Gallery — placeholder data
--
-- Loaded by init_db.py after schema.sql.
--
-- EVERY VALUE IN THIS FILE IS PLACEHOLDER CONTENT. No real artist, title,
-- date, medium or price appears here. Real Jansem and Carzou material is
-- added at Stage 21, from verified sources.
--
-- This file is the only thing that has to be replaced then. The schema, the
-- queries, the routes and the templates all stay exactly as they are.
-- =============================================================================


-- id is left out on purpose: SQLite assigns 1 and 2 automatically.
INSERT INTO artists (slug, name, lifespan, summary, bio, portrait) VALUES
    ('artist-one', 'Artist One', '1900-1980',
     'Placeholder artist description. One or two sentences introducing the artist and the character of their work.',
     'Placeholder biography paragraph. A longer passage about the artist, used on their collection page. Replaced with verified material at Stage 21.',
     'placeholders/artist-one.svg'),

    ('artist-two', 'Artist Two', '1905-1985',
     'Placeholder artist description. One or two sentences introducing the artist and the character of their work.',
     'Placeholder biography paragraph. A longer passage about the artist, used on their collection page. Replaced with verified material at Stage 21.',
     'placeholders/artist-two.svg');


-- artist_id is looked up by slug rather than typed as 1 or 2. The subquery
-- asks the database "which id belongs to this slug?", so the data stays
-- correct even if these rows are ever loaded in a different order.
INSERT INTO artworks
    (artist_id, title, year, medium, category, description, price_cents,
     available_for_purchase, inventory_quantity, is_featured,
     image, image_width, image_height)
VALUES
    -- A unique original: one of them, still for sale.
    ((SELECT id FROM artists WHERE slug = 'artist-one'),
     'Artwork Title', '2025', 'Oil on Canvas', 'Painting',
     'Placeholder artwork description.', 480000, 1, 1, 1,
     'placeholders/artwork-01.svg', 900, 1100),

    -- An edition: twelve of these prints remain.
    ((SELECT id FROM artists WHERE slug = 'artist-two'),
     'Artwork Title', '2025', 'Lithograph', 'Print',
     'Placeholder artwork description.', 125000, 1, 12, 1,
     'placeholders/artwork-02.svg', 1000, 800),

    -- Sold: offered for sale, but none left.
    ((SELECT id FROM artists WHERE slug = 'artist-one'),
     'Artwork Title', '2025', 'Ink on Paper', 'Drawing',
     'Placeholder artwork description.', 96000, 1, 0, 1,
     'placeholders/artwork-03.svg', 850, 1050),

    ((SELECT id FROM artists WHERE slug = 'artist-two'),
     'Artwork Title', '2025', 'Gouache on Paper', 'Painting',
     'Placeholder artwork description.', 210000, 1, 1, 1,
     'placeholders/artwork-04.svg', 700, 1200),

    -- Not for sale: on display only, so no price is shown.
    ((SELECT id FROM artists WHERE slug = 'artist-one'),
     'Artwork Title', '2025', 'Oil on Canvas', 'Painting',
     'Placeholder artwork description.', 640000, 0, 1, 1,
     'placeholders/artwork-05.svg', 1300, 800),

    -- Another edition, not featured on the homepage.
    ((SELECT id FROM artists WHERE slug = 'artist-two'),
     'Artwork Title', '2025', 'Etching', 'Print',
     'Placeholder artwork description.', 58000, 1, 25, 0,
     'placeholders/artwork-06.svg', 1000, 1000);
