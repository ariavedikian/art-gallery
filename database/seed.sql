-- =============================================================================
-- Art Gallery — the site's content
--
-- Loaded by init_db.py after schema.sql. This is what the site shows, and
-- every fact in it is real and cited:
--
--   * Each fact about an artist or a work has a row in artist_citations or
--     artwork_citations naming its source. tests/test_content.py fails on
--     any fact that has none.
--   * A fact nobody has verified is left out -- NULL, and the pages show
--     nothing for it -- never typed in to fill a gap.
--   * Facts are written in our own words from the source, never pasted.
--   * No placeholders. Those live in tests/seed.sql, which is what the tests
--     read; no test takes a value from this file.
--
-- Images: the artists' works and likenesses are not cleared for
-- reproduction (ADAGP manages both artists' rights), so every image here is
-- the neutral placeholders/no-image.svg until the owner has written
-- permission (Stage 21 Part 7).
-- =============================================================================


-- --- Sources -----------------------------------------------------------------
-- Both checked on 2026-10-09. Each ADAGP directory entry gives the artist's
-- name and years of birth and death ("Jean Jansem (1920 - 2013)"), and says
-- that ADAGP manages the artist's reproduction rights.
INSERT INTO sources (ref, citation, url, accessed) VALUES
    ('adagp-jansem', 'ADAGP, Répertoire des artistes: Jean Jansem',
     'https://www.adagp.fr/fr/repertoire-des-artistes?title=Jansem', '2026-10-09'),
    ('adagp-carzou', 'ADAGP, Répertoire des artistes: Jean Carzou',
     'https://www.adagp.fr/fr/repertoire-des-artistes?title=Carzou', '2026-10-09');


-- --- Artists -----------------------------------------------------------------
-- summary and bio are NULL: nothing about either artist's life or work has
-- been verified yet (Stage 21 Part 4). portrait_alt is NULL as well: the
-- neutral picture's alt text is derived in SQL ("Image not available").
INSERT INTO artists (slug, name, lifespan, summary, bio, portrait, portrait_alt) VALUES
    ('jean-jansem', 'Jean Jansem', '1920–2013', NULL, NULL,
     'placeholders/no-image.svg', NULL),
    ('jean-carzou', 'Jean Carzou', '1907–2000', NULL, NULL,
     'placeholders/no-image.svg', NULL);

INSERT INTO artist_citations (artist_id, field, source_id) VALUES
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'name',
     (SELECT id FROM sources WHERE ref = 'adagp-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'adagp-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'name',
     (SELECT id FROM sources WHERE ref = 'adagp-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'adagp-carzou'));


-- --- Artworks ----------------------------------------------------------------
-- None yet. The works shown will be works the owner holds, each identified
-- from its own evidence and confirmed by the owner (Stage 21 Part 5).
