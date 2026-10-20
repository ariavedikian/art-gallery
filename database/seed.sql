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
-- accessed is the day each page was read. Weighed in Stage 21 Part 4:
-- authority records and institutions speaking about their own business
-- first; the news obituary only where it adds a detail they lack (the
-- spelling Hovhannes, Issy-les-Moulineaux). Dealer listings, Wikipedia and
-- search summaries are not sources.
INSERT INTO sources (ref, citation, url, accessed) VALUES
    -- The rights society's directory: names, years, and who manages rights.
    ('adagp-jansem', 'ADAGP, Répertoire des artistes: Jean Jansem',
     'https://www.adagp.fr/fr/repertoire-des-artistes?title=Jansem', '2026-10-09'),
    ('adagp-carzou', 'ADAGP, Répertoire des artistes: Jean Carzou',
     'https://www.adagp.fr/fr/repertoire-des-artistes?title=Carzou', '2026-10-09'),

    -- The national library's authority records: names, births, deaths, notes.
    ('bnf-jansem', 'Bibliothèque nationale de France, data.bnf.fr: Jean Jansem (1920-2013)',
     'https://data.bnf.fr/fr/ark:/12148/cb11943683k', '2026-10-09'),
    ('bnf-carzou', 'Bibliothèque nationale de France, data.bnf.fr: Jean Carzou (1907-2000)',
     'https://data.bnf.fr/fr/ark:/12148/cb12595164w', '2026-10-09'),

    -- The academy Carzou belonged to, on its own member.
    ('academie-carzou', 'Académie des beaux-arts: Jean Carzou',
     'https://www.academiedesbeauxarts.fr/jean-carzou', '2026-10-09'),

    -- Museums on their own collections.
    ('paris-musees-jansem', 'Paris Musées collections: works by Jansem',
     'https://www.parismuseescollections.paris.fr/fr/recherche?keywords=Jansem', '2026-10-09'),
    ('paris-musees-carzou', 'Paris Musées collections: works by Carzou',
     'https://www.parismuseescollections.paris.fr/fr/recherche?keywords=Carzou', '2026-10-09'),
    ('maf-jansem', 'Musée Arménien de France: Jansem, Sister of the groom (1953)',
     'https://www.le-maf.com/en/item/jansem-1920-2013/', '2026-10-19'),
    ('agmi-2019', 'Armenian Genocide Museum-Institute, "Jansem: A Painter of Medz Yeghern", 18 June 2019',
     'https://www.genocide-museum.am/eng/18.06.2019_Jansem.php', '2026-10-09'),
    -- The museum's site answers only over http.
    ('azumino-museum', 'Azumino Jansem Museum (安曇野ジャンセン美術館)',
     'http://www.musee-de-jansem.jp/', '2026-10-09'),

    -- Armenia's national news agency, the day after Jansem's death. Its
    -- donation year (2001) and his age (94) are wrong; it is cited only
    -- for details the sources above confirm or do not cover.
    ('armenpress-2013', 'Armenpress, "World famous Jansem dies", 28 August 2013',
     'https://armenpress.am/en/article/730738', '2026-10-09');


-- --- Artists -----------------------------------------------------------------
-- Written from the facts the owner approved in Stage 21 Part 4, one sentence
-- at a time. Left out on purpose: Jansem's Arts et Lettres award (no
-- reliable source; the year often given, 1953, predates the order, created
-- in 1957), his place of death (the sources disagree), the exact village of
-- his birth (they disagree), and Carzou's day of birth (both sources give
-- 1 January, a common stand-in for an unknown day). portrait_alt is NULL:
-- the neutral picture's alt text is derived in SQL ("Image not available").
INSERT INTO artists (slug, name, lifespan, summary, bio, portrait, portrait_alt) VALUES
    ('jean-jansem', 'Jean Jansem', '1920–2013',
     'A painter, lithographer and sculptor of Armenian origin, born Hovhannes Semerdjian near Bursa in 1920, who came to France in 1931.',
     'Jansem was born Hovhannes Semerdjian on 9 March 1920, near Bursa in present-day Turkey, to an Armenian family. In the early 1920s his family fled persecution in Turkey and settled in Thessaloniki, Greece, where he grew up. In 1931 he came to France, to Issy-les-Moulineaux, just outside Paris. From the age of fourteen he took evening classes in Montparnasse, then studied at the École nationale supérieure des arts décoratifs from 1936, graduating in 1938. He worked as a painter, lithographer and sculptor. Between 1998 and 2001 he painted Yeghern, 34 canvases on the Armenian Genocide, and in 2002 gave the series to the Armenian Genocide Museum-Institute in Yerevan. He was made a chevalier of the Légion d''honneur in 2003, and received the Mesrop Mashtots medal from the President of Armenia. He died on 27 August 2013. His work is in the collections of the Musée d''Art Moderne de Paris and the Musée Arménien de France, and a museum in Azumino, Japan, is devoted to it.',
     'placeholders/no-image.svg', NULL),
    ('jean-carzou', 'Jean Carzou', '1907–2000',
     'A painter, engraver and stage designer, born Karnik Zouloumian in Aleppo, who settled in France in 1924 and was elected to the Académie des beaux-arts in 1977.',
     'Carzou was born Karnik Zouloumian in Aleppo, Syria, in 1907, and moved to France in 1924. He studied at the École Spéciale d''Architecture, graduating in 1928, and at the Académie de la Grande Chaumière, and held his first solo exhibition in 1939. A painter, draughtsman, engraver and lithographer, he returned again and again to Venice, Provence, imaginary ports, railways, palaces and ruins. He also designed sets for theatre and ballet, among them Les Indes galantes and Giselle, made tapestries for the Gobelins, worked on the decoration of the liner France, and illustrated books by writers including Hemingway and Camus. On 7 December 1977 he was elected to the painting section of the Académie des beaux-arts, succeeding Jean Bouchaud. A Musée Carzou opened at the Fondation Émile-Hugues in Vence in 1986, and in 1989 the Fondation Carzou was established in Manosque, in the Chapelle de la Présentation, whose walls he painted with the Apocalypse. He was an officier of the Légion d''honneur and a commandeur of the Ordre national du Mérite and of the Arts et Lettres. He died at Marsac-sur-l''Isle, in the Dordogne, on 12 August 2000. His work is in the collection of the Musée d''Art Moderne de Paris.',
     'placeholders/no-image.svg', NULL);

-- One row per (artist, fact, source). Each id is looked up by name, so a
-- mistyped ref finds nothing, and the NOT NULL on source_id refuses the row
-- loudly rather than letting the citation vanish.
INSERT INTO artist_citations (artist_id, field, source_id) VALUES
    -- Jean Jansem
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'name',
     (SELECT id FROM sources WHERE ref = 'adagp-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'name',
     (SELECT id FROM sources WHERE ref = 'bnf-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'adagp-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'bnf-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'summary',
     (SELECT id FROM sources WHERE ref = 'bnf-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'summary',
     (SELECT id FROM sources WHERE ref = 'armenpress-2013')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'bio',
     (SELECT id FROM sources WHERE ref = 'bnf-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'bio',
     (SELECT id FROM sources WHERE ref = 'maf-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'bio',
     (SELECT id FROM sources WHERE ref = 'agmi-2019')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'bio',
     (SELECT id FROM sources WHERE ref = 'paris-musees-jansem')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'bio',
     (SELECT id FROM sources WHERE ref = 'azumino-museum')),
    ((SELECT id FROM artists WHERE slug = 'jean-jansem'), 'bio',
     (SELECT id FROM sources WHERE ref = 'armenpress-2013')),

    -- Jean Carzou
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'name',
     (SELECT id FROM sources WHERE ref = 'adagp-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'name',
     (SELECT id FROM sources WHERE ref = 'bnf-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'adagp-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'bnf-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'lifespan',
     (SELECT id FROM sources WHERE ref = 'academie-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'summary',
     (SELECT id FROM sources WHERE ref = 'bnf-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'summary',
     (SELECT id FROM sources WHERE ref = 'academie-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'bio',
     (SELECT id FROM sources WHERE ref = 'bnf-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'bio',
     (SELECT id FROM sources WHERE ref = 'academie-carzou')),
    ((SELECT id FROM artists WHERE slug = 'jean-carzou'), 'bio',
     (SELECT id FROM sources WHERE ref = 'paris-musees-carzou'));


-- --- Artworks ----------------------------------------------------------------
-- None yet. The works shown will be works the owner holds, each identified
-- from its own evidence and confirmed by the owner (Stage 21 Part 5).
