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
- **Numeric URL parameters use `<int:...>`.** The converter refuses
  non-numbers at the routing table, before any code runs, and hands the
  view a real int rather than a string.
- **JavaScript is an enhancement, never the only path.** Every card is a
  real link to a real page; the lightbox intercepts the click. With JS off
  the site still works, and modifier-clicks are left alone.
- **Use the platform before writing it yourself** (`<dialog>` for modal
  behaviour, focus handling and the backdrop). Where a built-in could not
  be verified, add a documented fallback rather than trusting it blindly.
- **One rule, one place.** `_STATUS_CASE` in app.py derives a `status`
  column (for-sale / sold / not-for-sale) in SQL. The price line, the
  purchase block and the availability filter all read that one definition.
- **Filtering and sorting happen in SQL**, with the filters in the query
  string so a filtered view has a URL and works without JavaScript. Query
  STRUCTURE may be built in Python; VALUES always travel as ? parameters.
- **Validate values that came from a URL** against a known set (see
  `PRICE_RANGES`) rather than trusting them.
- **Business rules are written once.** The lightbox copies the rendered
  price line out of the card rather than reimplementing the Sold and
  edition logic in JavaScript.
- **Not found is a 404, never a 200.** Error templates are returned as
  `render_template(...), 404` so the status code matches the page.
- **One grid, one macro.** Every page showing artworks calls
  `artwork_grid(...)`; no page writes its own `<ul class="artwork-grid">`.
- **Store facts, derive conclusions.** `available_for_purchase` and
  `inventory_quantity` are stored; Sold is worked out from them.
- **The cart lives in the signed session cookie** and stores exactly one
  thing: `{artwork_id: quantity}`. Titles, prices and availability are read
  from the database on every request. A price that arrives from the client is
  a price the client chose.
- **Session keys are strings.** A session is serialised to JSON before it is
  signed, so `4` goes in and `"4"` comes back. Cart code uses `str(id)`.
- **Assign to the session, never mutate it in place.** Flask re-sends the
  cookie only when it notices a change, and it cannot notice a mutation
  inside a dict it handed you.
- **Anything that changes state is a POST followed by a redirect**
  (POST/Redirect/GET), so a reload never repeats the action. Reads stay GET,
  which is why filters are GET and `/cart/add` is not.
- **A cart reserves nothing.** Availability is checked when a work is added
  and re-derived every time the cart is rendered, but the only check that
  counts is the atomic one inside the checkout transaction (Stage 12/13).
  The artwork page says so in plain words.
- **A rule enforced only in a template is not enforced.** The Add to cart
  button is rendered only for a work that is for sale, and `/cart/add`
  checks `status` again, because a POST can arrive without that page ever
  being loaded.
- **A cart line with a problem is shown, not silently corrected**, and left
  out of the subtotal. The visitor decides what to do about it.
- **`SECRET_KEY` comes from `ART_GALLERY_SECRET_KEY`**, with a dev fallback so
  the app runs out of the box. Stage 20 revisits this properly.
- **Transactions are explicit.** The connection is opened with
  `isolation_level=None`, so Python never opens or commits one behind your
  back. `place_order()` is the only writer and manages its own
  `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`.
- **Check and claim in one statement.** Inventory is taken with
  `UPDATE ... SET quantity = quantity - ? WHERE id = ? AND quantity >= ?`,
  then `cursor.rowcount` says whether it worked. SELECT-then-decide-then-UPDATE
  has a gap in the middle, and two buyers fit inside it.
- **Redirect on success, re-render on failure.** A rejected form comes back
  with its errors and everything already typed, and a 400 status. Only a
  successful write redirects.
- **A bad request is a 400**, the same conviction as 404 for not found.
- **Validation is server-side.** `novalidate` is on the checkout form on
  purpose, so the server's checks are what you see while testing.
- **Public identifiers are random, not sequential.** An order is found by
  `secrets.token_urlsafe(16)`, because `/order/3` invites `/order/2`.
- **A record of the past stores values, not pointers.** `order_items` keeps
  `title_at_purchase`, `artist_at_purchase` and `unit_price_cents`; repricing
  a work must never rewrite a receipt. `artwork_id` is kept only for the link.
- **Mock payment is labelled unmistakably**, in the form and on the receipt,
  and is selectable approve/decline so the failure path can be tested.
- **Tests build their own throwaway database** from `schema.sql` and
  `seed.sql` in a temp folder and point `app.DATABASE_PATH` at it, via
  `tests/support.py`. A test that can destroy the database you are working on
  is worse than no test.
- **Tests inspect the database on their own connection**, not through the code
  under test. A test that checks its subject through its subject can agree
  with a bug instead of catching it.
- **Orders this browser remembers** live in the session as a list of
  references; the database holds everything true about them. Same arrangement
  as the cart, one level up. Without accounts, "your orders" can only mean
  "this browser's orders" — which is what Stage 16 fixes.
- **The status vocabulary is stated twice** — `ORDER_STATUSES` in app.py and a
  `CHECK` constraint in schema.sql — because SQLite cannot read a Python dict.
  `tests/test_order_snapshot.py` fails the moment the two disagree.
- **Tests are plain scripts** run with `python tests/<name>.py`, stdlib only,
  exiting non-zero on failure. No pytest until there are enough tests to earn
  the dependency.
- **Concurrency is tested with threads, never by hand.** Clicking through the
  site does one thing at a time and can never produce the situation the
  checkout transaction exists for. See `tests/test_checkout_race.py`.
- **Parameterised SQL only** (`WHERE id = ?`). Never f-string user input into
  a query.
- Prices are stored as **integer cents**, never floats (added Stage 5).
- The data model must support both one-of-a-kind originals and multi-copy
  editions.
- **Artworks are never cropped.** Show them with `object-fit: contain` inside
  a `.mat`. Photographs of people (artist portraits) may use `cover`.
- **Artwork titles are italic** (`.work-title`), the art-writing convention.
- **Hover effects only on interactive elements.** A hover promises a click.
  Artwork cards became links at Stage 8 and got one then.
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

Run the tests with:

```powershell
python tests/test_checkout_race.py
python tests/test_order_snapshot.py
```

## Layout

```
art-gallery/
├── app.py            # Flask application: routes + (for now) placeholder data
├── requirements.txt  # pinned dependencies
├── CLAUDE.md         # this file
├── README.md         # how to run it
├── templates/        # base, index, gallery, artist, artwork, cart,
│                  #   checkout, order, orders, 404, macros
├── static/           # css/style.css, js/{lightbox,filter}.js, images/
├── init_db.py        # rebuilds the database from SQL files
├── tests/            # plain runnable scripts, stdlib only (no pytest yet);
│                  #   support.py holds the throwaway-database helpers
└── database/         # schema.sql (artists, artworks, orders, order_items),
                  #   seed.sql, art_gallery.db (generated)
```

## Stage roadmap

Status: `[x]` done · `[~]` partly done · `[ ]` not started

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
- [x] **8 — Artwork detail page.** `/artwork/<id>`, fetching one record,
      handling a missing record, 404 vs 500.
- [x] **9 — JavaScript interactivity.** Lightbox viewer: DOM manipulation,
      event listeners, client state, keyboard nav, Escape/click-outside.
- [x] **10 — Search & filtering.** Built twice on purpose: first in the
      browser over the cards already on the page, then in SQL with the filters
      in the query string. The SQL version is what ships.
- [x] **11 — Shopping cart.** Sessions, cart state, add/remove/quantity,
      subtotal, inventory rules for one-of-a-kind pieces.
- [x] **12 — Checkout.** POST requests, form handling, validation, order
      creation, database transactions. Clearly-labelled MOCK payment flow.
      Created `orders` and `order_items` (with the price snapshot), since an
      order cannot be written without them.
- [x] **13 — Order system.** Status vocabulary with a CHECK constraint,
      remembered orders per browser (`/orders`), and the snapshot proved by
      test rather than asserted. Transition RULES deliberately deferred to the
      stages that can perform transitions (14 webhook, 16 admin).
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
