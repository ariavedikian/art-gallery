# Art Gallery — project guide

A full-stack digital gallery and art marketplace for the work of **Jean Jansem**
and **Jean Carzou**. Built from scratch as a teaching project: the goal is for
the owner to understand every layer, not just to ship a site.

## Stack (deliberately constrained)

| Layer | Choice | Why |
|---|---|---|
| Frontend | HTML, CSS, vanilla JavaScript | learn the fundamentals, no framework abstraction |
| Backend | Python 3.13 + Flask | micro-framework; we write every step ourselves |
| Database | SQLite + raw SQL | see the actual queries, no ORM magic |
| Payments | Stripe (test mode), Stage 14 only | never handle card data ourselves |

Do **not** introduce React, Next.js, Django, or an ORM without a compelling
reason and an explicit discussion first.

## Hard rules

1. **Placeholder-first.** Build the entire architecture on `"Artist One"`,
   `"Artwork Title"`, `"2025"`, `"Oil on Canvas"`, placeholder images. Real
   artist content is Stage 21 and Stage 21 only. The architecture must not need
   to change when placeholders are swapped for real data — if it does, the
   design was wrong.
2. **Never fabricate.** No invented biographies, artwork titles, dates,
   mediums, museums, provenance, or prices for Jansem or Carzou. Real content
   comes from verifiable sources, or it does not go in.
3. **Stage-gated.** One stage at a time. Finish it, give a test checklist,
   then STOP and wait for review before starting the next.
4. **Teach, don't dump.** For each stage: explain the goal, explain the new
   concepts in beginner terms, say which files change, implement, explain the
   important parts, give a checklist. When debugging, explain the cause rather
   than silently replacing code.
5. **No sensitive data in the database.** Never store raw card numbers, CVVs,
   or payment credentials.

## Design direction

A digital museum, not a storefront. Minimalist, typography-driven, spacious,
image-first. The artwork always dominates the visual hierarchy; commerce is
integrated quietly rather than bolted on.

Avoid: heavy gradients, excessive animation, generic developer-portfolio
styling, cluttered layouts.

## Conventions

- **Routes never touch data directly.** They call data-access functions in
  `app.py` (`get_artist`, `get_artworks_by_artist`, ...). At Stage 6 only those
  function bodies change to SQL; routes and templates stay the same.
- **Site-wide template variables** (`gallery_name`, `nav_artists`) come from
  the `inject_site_globals` context processor, never from individual routes.
- **Shared template pieces** live in `templates/macros.html` and are imported
  with `{% from "macros.html" import ... %}`.
- **Build URLs with `url_for`**, never hardcoded strings.
- **Routes have no trailing slash** (`/artists`, `/cart`, `/artwork/123`).
  Werkzeug treats `/x` and `/x/` differently; one consistent style avoids
  surprise 404s and redirects.
- **Placeholder images** live in `static/images/placeholders/` and are visibly
  labelled as placeholders. Real images arrive in `static/images/jansem/` and
  `static/images/carzou/` at Stage 17/21.
- **The database is generated, never edited by hand.** `database/schema.sql`
  and `database/seed.sql` are the source of truth; rebuild the .db file with
  `python init_db.py --reset`. The .db file is gitignored.
- **One connection per request**, opened lazily by `get_db()` on Flask's `g`
  and closed by the `teardown_appcontext` handler. Never open a connection
  inside a loop or at import time.
- **Rows use `sqlite3.Row`**, so templates can write `{{ art.title }}`.
  Plain tuples render as empty strings in Jinja, silently.
- **Turn foreign keys on** with `PRAGMA foreign_keys = ON` on every
  connection. SQLite does not enforce them otherwise.
- **SQLite has no BOOLEAN or DATE type.** Use 0/1 for flags and ISO text
  for dates. Artwork `year` is TEXT, since art dates can be approximate.
- **Sorting and filtering belong in SQL**, not in Jinja or Python. Which
  works appear and in what order is decided by the query; templates only
  decide how a work looks.
- **`display_order`** is the gallery running order (lower first, seeded in
  steps of 10). The lowest-numbered featured work is the homepage spotlight.
- **One grid, one macro.** Every page showing artworks calls
  `artwork_grid(...)`; no page writes its own `<ul class="artwork-grid">`.
- **Store facts, derive conclusions.** `available_for_purchase` and
  `inventory_quantity` are stored; Sold is worked out from them.
- **Parameterised SQL only** (`WHERE id = ?`). Never f-string user input into
  a query.
- Prices are stored as **integer cents**, never floats (added Stage 5).
- The data model must support both one-of-a-kind originals and multi-copy
  editions.
- **Artworks are never cropped.** Show them with `object-fit: contain` inside
  a `.mat`. Photographs of people (artist portraits) may use `cover`.
- **Artwork titles are italic** (`.work-title`), the art-writing convention.
- **Hover effects only on interactive elements.** A hover promises a click;
  artwork cards get none until they link somewhere (Stage 8).
- **Visual-only decisions live in CSS**, not Jinja conditionals (for example
  the alternating artist layout uses `:nth-of-type(even)`).
- **Type:** Cormorant Garamond for display sizes only, Inter for text.
  Loaded from Google Fonts for now; self-host at Stage 19 for privacy and speed.

## Running it

```powershell
cd "C:\Users\ariav\ICS\Claude Projects\art-gallery"
.\venv\Scripts\Activate.ps1
python app.py          # http://127.0.0.1:5000
```

`venv/` is disposable and gitignored; rebuild with
`python -m venv venv` then `pip install -r requirements.txt`.

## Layout

```
art-gallery/
├── app.py            # Flask application: routes + (for now) placeholder data
├── requirements.txt  # pinned dependencies
├── CLAUDE.md         # this file
├── README.md         # how to run it
├── templates/        # base, index, gallery, artist, macros
├── static/           # css/ js/ images/
├── init_db.py        # rebuilds the database from SQL files
└── database/         # schema.sql, seed.sql, art_gallery.db (generated)
```

## Stage roadmap

Status: `[x]` done · `[ ]` not started

- [x] **1 — Environment & Flask basics.** venv, requirements.txt, first routes,
      request/response cycle, localhost, status codes.
- [x] **2 — Basic website.** Jinja templates, `render_template`, template
      inheritance, static files, semantic HTML, CSS fundamentals, the homepage
      (nav, hero, intro, two artist sections, featured works, footer).
- [x] **3 — Gallery design.** Elevate the landing page: artist cards, featured
      artwork, CSS Grid, responsive layouts, hover/transition, accessibility.
- [x] **4 — Artist pages & routes.** `/artists/<slug>`, URL parameters, one
      route serving many artists, passing Python data into templates.
- [x] **5 — Database introduction.** SQLite, `schema.sql`, `artists` and
      `artworks` tables, primary/foreign keys, CRUD, why not hardcode.
- [x] **6 — Connect Flask to SQLite.** Connections, parameterised queries,
      passing rows to templates, safe handling of user input.
- [x] **7 — Dynamic artwork gallery.** Database-driven artwork cards, Jinja
      loops, separating data from presentation.
- [ ] **8 — Artwork detail page.** `/artwork/<id>`, fetching one record,
      handling a missing record, 404 vs 500.
- [ ] **9 — JavaScript interactivity.** Lightbox viewer: DOM manipulation,
      event listeners, client state, keyboard nav, Escape/click-outside.
- [ ] **10 — Search & filtering.** Client-side filtering first, then the same
      job in SQL — the frontend vs backend processing tradeoff.
- [ ] **11 — Shopping cart.** Sessions, cart state, add/remove/quantity,
      subtotal, inventory rules for one-of-a-kind pieces.
- [ ] **12 — Checkout.** POST requests, form handling, validation, order
      creation, database transactions. Clearly-labelled MOCK payment flow.
- [ ] **13 — Order system.** `orders` / `order_items`; store price at time of
      purchase, not a live reference to the artwork's current price.
- [ ] **14 — Real payments.** Stripe test mode, checkout sessions, webhooks,
      payment confirmation and failure, order status.
- [ ] **15 — API / JSON.** `/api/...` endpoints, GET/POST, `fetch()`, why APIs
      are useful.
- [ ] **16 — Admin / CMS.** Add/edit/delete artwork, pricing, availability,
      featured flag. Simple auth.
- [ ] **17 — Image management.** Static file organisation, naming conventions,
      optimisation, safe upload concepts.
- [ ] **18 — Responsive polish.** Media queries, responsive type and grids,
      mobile navigation, tested across breakpoints.
- [ ] **19 — Performance & accessibility.** Lazy loading, alt text, keyboard
      navigation, contrast, query efficiency.
- [ ] **20 — Security basics.** Input validation, SQL injection, output
      escaping, sessions, CSRF, protecting admin, payment architecture.
- [ ] **21 — Real content.** Artist One → Jean Jansem, Artist Two → Jean
      Carzou. Verified sources only. Architecture should not change.
- [ ] **22 — Final refactor.** Duplication, naming, dead code, query
      efficiency, error handling, broken links, console errors.

## Architecture the owner should be able to narrate

```
Browser → Flask route → Python logic → SQLite → Flask → template → Browser
```

and for purchases:

```
Browser → Flask → DB → Payment provider → webhook → Flask → DB → confirmation
```
