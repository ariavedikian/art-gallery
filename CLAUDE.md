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
- **The API is a second format over the same functions.** `/api/...` routes
  call the same data-access functions as the pages (`search_artworks`,
  `get_artwork`) and the same rule functions (`add_to_cart`, `filters_from`).
  A route chooses a format; it never re-implements a rule.
- **The JSON shape is a contract.** `artwork_json()` builds each object field
  by field; a new database column never appears in the API by accident.
  `tests/test_api.py` pins the exact field list.
- **Business rules apply to the API too.** No price for a work that is not
  for sale, in JSON exactly as on the page.
- **API errors are JSON with honest status codes**: 400 malformed, 404 not
  found, 405 wrong method (with `Allow`), 409 refused by the work's state.
  Outside `/api/` errors stay HTML.
- **JSON types are checked, not coerced.** `"2"` is not `2`, and `true` is not
  `1` even though Python's `bool` is an `int`.
- **fetch() enhances a working form.** The form keeps a real `action=` and
  gets `data-api=` for the script. On any failure the script falls back to
  `form.submit()`, which does not re-fire the submit event.
- **Elements JavaScript updates are always rendered**, hidden when empty
  (the nav cart count), since a script cannot update an element that was
  never in the page.
- **Passwords are stored only as Werkzeug hashes** (salted, deliberately
  slow). Never hand-rolled, never logged, never sent back inside a page.
- **No credential lives in a committed file.** `seed.sql` creates no admin;
  `flask create-admin` prompts for the password without echoing it.
- **Every admin route carries `@admin_required`, below `@app.get`/`@app.post`.**
  Decorators apply bottom-up; the other order registers the unlocked view.
  `tests/test_admin.py` walks the whole routing table, so a new /admin route
  that forgets the lock fails the suite.
- **The session holds the admin's id; the database decides.** `current_admin()`
  re-reads the row each request, so deleting an admin locks them out at once.
- **One message for every failed login**, and a dummy hash check for unknown
  usernames, so neither the wording nor the timing reveals which exist.
- **`next=` is honoured only if it is a path on this site** (`safe_next()`):
  no scheme, no host, not `//`, no backslash. Otherwise, an open redirect.
- **Logout is a POST**, and only removes the admin key; the visitor's cart and
  remembered orders belong to the browser, not the login.
- **Admin responses are `Cache-Control: no-store`**, and admin pages carry
  `noindex`. The public site never links to `/admin`.
- **The session cookie is `SameSite=Lax`**, set explicitly rather than trusted
  to browser defaults. Full CSRF protection is Stage 20.
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

## Deferred: Stage 14 (real payments)

Stage 14 was skipped and still has to be done. Nothing from it is in the code
yet apart from two installed, pinned dependencies (`stripe`, `python-dotenv`
in `requirements.txt`). Checkout still uses the clearly-labelled mock.

**To do before starting (you, not Claude):**

- [ ] Create a Stripe account. Test mode needs no business details.
- [ ] Get your **test** API keys from the Stripe dashboard (they start
      `sk_test_`). Put them in a `.env` file yourself; `.env` is gitignored.
      Never paste keys into a chat or commit them.
- [ ] Install the Stripe CLI, which forwards webhooks to `localhost` while
      developing.

**To do in the code:**

- [ ] Write `payments.py`, the one module that talks to Stripe. `app.py`
      should never import `stripe` directly, so tests can swap in a fake and
      a change of provider touches one file.
- [ ] Refuse any key that is not a test key, in code.

**The design worked out before it was deferred** (about our own code, not
Stripe's):

- A `ROLLBACK` can undo database rows but cannot un-charge a card, and the
  payment now happens outside our request. So the single Stage 12
  transaction becomes a lifecycle: claim the stock and write the order as
  `pending`, commit, send the buyer to pay; the webhook later moves it to
  `paid` or `cancelled`.
- The success page the buyer returns to proves nothing. Only a
  signature-verified webhook confirms a payment.
- Every status change is a guarded check-and-claim, so duplicate or
  out-of-order webhooks are harmless:
  `UPDATE orders SET status = 'paid' WHERE reference = ? AND status = 'pending'`.
- Cancelling is compensation, not rollback: a new transaction moves
  `pending → cancelled` and returns the stock, with the same status guard
  making sure stock comes back exactly once.
- Stock is held while payment is pending, but the hold must have an expiry,
  plus a sweep that releases expired holds in case a webhook never arrives.
- Stage 13 left the transition rules unwritten on purpose. Stage 14 writes
  the ones the webhook performs: `pending → paid`, `pending → cancelled`.

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
python tests/test_api.py
python tests/test_admin.py
```

Create (or re-password) an admin. The database starts with none, and
`init_db.py --reset` empties the table again:

```powershell
flask --app app create-admin yourname
```

## Layout

```
art-gallery/
├── app.py            # Flask application: routes + (for now) placeholder data
├── requirements.txt  # pinned dependencies
├── CLAUDE.md         # this file
├── README.md         # how to run it
├── templates/        # base, index, gallery, artist, artwork, cart,
│                  #   checkout, order, orders, 404, macros;
│                  #   admin/ holds login and dashboard
├── static/           # css/style.css, js/{lightbox,filter,cart}.js, images/
├── init_db.py        # rebuilds the database from SQL files
├── tests/            # plain runnable scripts, stdlib only (no pytest yet);
│                  #   support.py holds the throwaway-database helpers
└── database/         # schema.sql (artists, artworks, orders, order_items,
                  #   admins),
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
- [ ] **14 — Real payments. DEFERRED — come back to this.** Stripe test
      mode, checkout sessions, webhooks, payment confirmation and failure,
      order status. Skipped on 2026-09-24 and moved on to Stage 15; the mock
      checkout from Stage 12 is still what runs. See "Deferred: Stage 14"
      below for the to-do list.
- [x] **15 — API / JSON.** `/api/...` endpoints, GET/POST, `fetch()`, why APIs
      are useful. `GET /api/artworks` (same filters as All works),
      `GET /api/artworks/<id>`, `POST /api/cart`; Add to cart uses it via
      `static/js/cart.js`, falling back to the plain form.
- [~] **16 — Admin / CMS.** Add/edit/delete artwork, pricing, availability,
      featured flag. Simple auth. Split in two, like Stage 10.
      **Part 1 done:** `admins` table with hashed passwords,
      `flask create-admin`, login/logout, `@admin_required`, safe `next=`,
      read-only dashboard. **Part 2 to do:** create/edit/delete artworks with
      validation, and marking orders shipped (`paid → shipped`).
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
