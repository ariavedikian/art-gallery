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
     'https://armenpress.am/en/article/730738', '2026-10-09'),

    -- The owner's works (Stage 21 Part 5). No web address: both are in the
    -- owner's hands, and the owner can check them.
    --
    -- The works themselves: what is written on each sheet (signature,
    -- date, numbering, title), read from the owner's photographs. The
    -- primary evidence for its own inscriptions, so where the two disagree,
    -- the sheet of paper wins over the description sheet.
    ('works-themselves', 'The works themselves: inscriptions read from the owner''s photographs',
     NULL, NULL),
    -- Printed description sheets in French, English and Armenian, kept
    -- with the works; photographed on 29 October 2026. They give title,
    -- year, medium and size. Some of their edition numbers disagree with
    -- the pencil numbers on the prints (see the artworks below), and one
    -- English size is plainly wrong (70 inches for 70 cm), so only the
    -- centimetre sizes are used.
    ('owner-description-sheets', 'Description sheets in the owner''s files (French, English, Armenian)',
     NULL, NULL);


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
-- The owner's works (Stage 21 Part 5): 10 by Carzou, 9 by Jansem, matched
-- to the owner's description sheets. Titles are the sheets' French titles,
-- with the English one in brackets. Ids are written out (works have no
-- slug); display_order runs by artist, then date.
--
-- Facts only, as cited below. Editions the owner settled on 29 October
-- 2026, where the sheet and the pencil number seemed to disagree or the
-- pencil was hard to read in the photograph:
--   * from the sheet, so cited to the sheets alone: La dame, Rivage,
--     Femme de profil avec bouquets (the French sheet's 172/173; the
--     English one says 172/172), Souvenir de Bretagne, Mère et enfants au
--     parapluie (the pencil could be 1/15 or 7/15)
--   * from the print, so cited to the work: La reine masquée, whose pencil
--     reads 117/150 where the sheet says 64/150
-- Left NULL until the owner settles them:
--   * the edition of Femme au fichu noir de dos: the sheet gives none, and
--     the pencil number is illegible in the photograph
--   * year and size, where the sheet gives none.
-- The dedication on Les soliloques du pauvre is left out at the owner's
-- request.
--
-- Not facts, so not cited: price, stock (one sheet each), for sale or not,
-- featured, running order -- the owner's decisions. Until the owner sets
-- prices, every work is shown as not for sale. Every image is the neutral
-- picture until reproduction is authorised (Part 7).
INSERT INTO artworks
    (id, artist_id, title, year, medium, category, description,
     dimensions, edition, inscriptions,
     price_cents, available_for_purchase, inventory_quantity, is_featured,
     image, image_width, image_height, display_order)
VALUES
    (1, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Bateaux (I) (Boats (I))', '1958',
     'Etching', 'Print', NULL,
     '40 × 29 cm', '190/350',
     'Signed and dated in the plate lower left; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 10),
    (2, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Voici, des fleurs, des fruits… (Here are the flowers, the fruits…)', '1962',
     'Color lithograph', 'Print', NULL,
     '49 × 70 cm', 'E.A. (artist''s proof)',
     'Signed and dated in pencil lower right; inscribed E.A. lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 20),
    (3, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'La dame (The lady)', '1965',
     'Etching enhanced with drypoint, in black', 'Print', NULL,
     '46 × 63 cm', '50/50',
     'Signed and dated in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 30),
    (4, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Aurora', '1970',
     'Color lithograph', 'Print', NULL,
     '46 × 56.5 cm', '70/150',
     'Signed and dated in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 40),
    (5, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'La reine masquée (The masked queen)', '1970',
     'Color lithograph', 'Print', NULL,
     '49 × 71 cm', '117/150',
     'Signed and dated in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 50),
    (6, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Rivage (Shore)', '1972',
     'Color lithograph', 'Print', NULL,
     '50 × 66 cm', 'Épreuve sur Japon 12/75 (proof on Japan paper)',
     'Signed and dated in pencil lower right; inscribed Épreuve sur Japon and numbered lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 60),
    (7, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Femme de profil avec bouquets (Profile of woman with flowers)', '1973',
     'Color lithograph', 'Print', NULL,
     '52 × 67 cm', '172/173',
     'Signed and dated in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 70),
    (8, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Le château de Rochechouart (The castle of Rochechouart)', '1978',
     'Color lithograph', 'Print', NULL,
     '53 × 67 cm', 'Épreuve sur Japon 4/25 (proof on Japan paper)',
     'Signed and dated in pencil lower right; titled lower centre; inscribed Épreuve sur Japon and numbered lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 80),
    (9, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Souvenir de Bretagne (Souvenir from Bretagne)', '1986',
     'Color lithograph', 'Print', NULL,
     '52 × 69 cm', 'Épreuve sur Japon 4/150 (proof on Japan paper)',
     'Signed and dated in pencil lower right; titled lower centre; inscribed Épreuve sur Japon and numbered lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 90),
    (10, (SELECT id FROM artists WHERE slug = 'jean-carzou'),
     'Le rivage perdu (The lost shore)', '1989',
     'Color lithograph', 'Print', NULL,
     '48 × 62 cm', 'XXXVIII/L',
     'Signed and dated in pencil lower right; titled lower centre; numbered lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 100),
    (11, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Mère et enfants au parapluie (Mother and daughters with umbrella)', 'c. 1960',
     'Lithograph, black and white', 'Print', NULL,
     '24 × 16.5 cm', '1/15',
     'Signed in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 110),
    (12, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Les quais (The docks)', '1966',
     'Color lithograph', 'Print', 'A view of Venice. Listed in Jansem Oeuvres Graphiques, page 27.',
     '43 × 57 cm', 'E.A. XXV/XXX (artist''s proof)',
     'Signed in pencil lower right; inscribed E.A. and numbered lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 120),
    (13, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Esperanza', '1968',
     'Color lithograph', 'Print', 'Listed in Jansem Oeuvres Graphiques, page 37.',
     '54 × 39.5 cm', '116/120',
     'Signed in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 130),
    (14, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Corrida en Espagne. La mise à mort (Corrida in Spain. The death)', '1971',
     'Color lithograph', 'Print', NULL,
     '35.5 × 53 cm', '5/140',
     'Signed in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 140),
    (15, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Spectateurs (Spectators)', '1971',
     'Color lithograph', 'Print', NULL,
     '35.5 × 53 cm', '122/140',
     'Signed in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 150),
    (16, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Taureau (The Bull)', '1971',
     'Color lithograph', 'Print', NULL,
     '35.5 × 53 cm', '19/120',
     'Signed in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 160),
    (17, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Femme au fichu noir de dos (Woman with a black scarf)', '1973',
     'Color lithograph', 'Print', NULL,
     '66.5 × 48.5 cm', NULL,
     'Signed in pencil lower right; numbered in pencil lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 170),
    (18, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Les soliloques du pauvre (The soliloquies of the poor)', NULL,
     'Mixed technique', 'Mixed media', 'Listed in Jansem Oeuvres Graphiques, page 54.',
     NULL, NULL,
     'Signed lower right, within the image.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 180),
    (19, (SELECT id FROM artists WHERE slug = 'jean-jansem'),
     'Femme au chapeau (Woman in hat)', NULL,
     'Ink and color on paper', 'Painting', NULL,
     '64.75 × 49.5 cm', NULL,
     'Signed lower left.',
     0, 0, 1, 0, 'placeholders/no-image.svg', 800, 1000, 190);

INSERT INTO artwork_citations (artwork_id, field, source_id) VALUES
    (1, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (1, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (1, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (1, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (1, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (1, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (1, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (1, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (1, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (2, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (2, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (2, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (2, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (2, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (2, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (2, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (2, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (2, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (3, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (3, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (3, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (3, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (3, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (3, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (3, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (3, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (4, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (4, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (4, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (4, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (4, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (4, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (4, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (4, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (4, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (5, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (5, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (5, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (5, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (5, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (5, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (5, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (5, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (6, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (6, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (6, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (6, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (6, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (6, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (6, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (6, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (7, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (7, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (7, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (7, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (7, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (7, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (7, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (7, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (8, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (8, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (8, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (8, 'title', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (8, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (8, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (8, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (8, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (8, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (8, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (9, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (9, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (9, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (9, 'title', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (9, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (9, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (9, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (9, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (9, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (10, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (10, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (10, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (10, 'title', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (10, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (10, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (10, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (10, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (10, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (10, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (11, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (11, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (11, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (11, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (11, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (11, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (11, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (11, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (12, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (12, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'description', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (12, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (12, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (13, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (13, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'description', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (13, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (13, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (14, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (14, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (14, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (14, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (14, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (14, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (14, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (14, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (14, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (15, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (15, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (15, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (15, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (15, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (15, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (15, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (15, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (15, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (16, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (16, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (16, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (16, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (16, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (16, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (16, 'edition', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (16, 'edition', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (16, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (17, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (17, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (17, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (17, 'year', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (17, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (17, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (17, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (18, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (18, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (18, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (18, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (18, 'description', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (18, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (19, 'artist', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (19, 'artist', (SELECT id FROM sources WHERE ref = 'works-themselves')),
    (19, 'title', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (19, 'medium', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (19, 'dimensions', (SELECT id FROM sources WHERE ref = 'owner-description-sheets')),
    (19, 'inscriptions', (SELECT id FROM sources WHERE ref = 'works-themselves'));
