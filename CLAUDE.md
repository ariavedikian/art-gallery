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
| Images | Pillow (Stage 17) | decoding untrusted uploads is not something to hand-roll |

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
  labelled as placeholders. Uploaded images live in `static/images/artworks/`
  (gitignored, like the database: content, not code), one flat folder for
  every artist. Which artist a work belongs to is a database fact the admin
  can edit; a folder name would go stale.
- **The database is generated, never edited by hand.** `database/schema.sql`
  and `database/seed.sql` are the source of truth; rebuild the .db file with
  `python init_db.py --reset`. The .db file is gitignored.
- **The schema has a version number.** `schema.sql` sets `PRAGMA user_version`;
  `SCHEMA_VERSION` in app.py must match, and `get_db()` refuses any other
  (once per file per process), naming `init_db.py --reset`. Any change to a
  table, column or index: bump both. A stale file used to fail later as
  "no such column: aw.alt_text" (Stage 20, the owner's own database, built
  before Stage 19). Tests never see a stale file, since they build a fresh
  one, which is why this check exists.
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
- **Breakpoints come from the content, in em.** A layout breaks where its
  content stops fitting, not at a list of device sizes: the header's 64em
  is where the wordmark and nav (about 965px, measured) no longer fit one
  row. em, so a reader who enlarges their text gets the narrow layout
  sooner. Written as range syntax, `@media (width < 64em)`; the one-column
  layout is `(width < 50em)`. If the gallery name or artist names grow at
  Stage 21, re-measure. `tests/test_layout.py` fails on a px breakpoint.
- **Measure layout, don't eyeball it.** Before and after layout work, load
  every page into fixed-width iframes (320-1440px) and measure page
  overflow, element sizes and tap targets; `sandbox` without
  `allow-scripts` shows the JavaScript-off version. Elements inside a
  scrolling box do not count as overflowing the page.
- **Targets are at least 24px** (WCAG 2.2, 2.5.8), by padding rather than
  bigger text; 44px for the phone header's buttons. Links inside running
  content, with clear space around them, meet it by spacing and are left
  alone. No text below 0.6875rem (11px); `test_layout.py` enforces it.
- **A scrolling box that holds `.visually-hidden` text is positioned.** That
  text is `position: absolute`, and it belongs to its nearest POSITIONED
  ancestor: without `position: relative` on `.admin-table-wrap` it escaped
  the scroll and stretched the page to 557px at 320px wide.
- **Fieldsets get `min-inline-size: 0`.** Browsers default it to
  `min-content`, so a fieldset can never be narrower than its widest
  child (a long select option), and pushes the page sideways on a phone.
- **Admin tables scroll sideways on a phone, first column pinned**
  (`position: sticky`). Cards would lose comparing down a column.
- **The phone menu is switched on by its script.** `static/js/nav.js` adds
  `site-header--menu` to the header; only then does the CSS show the Menu
  button and fold the links away. With JavaScript off, or if the script
  fails, every link stays visible. The button's `display` is set in ONE rule,
  `.site-header--menu .menu-toggle`; `tests/test_navigation.py` fails if any
  other rule sets it (one did, and showed a dead button with JS off).
- **A widget's state lives in one ARIA attribute.** The menu is open when the
  button's `aria-expanded` is "true": the script flips it, the CSS reads it
  (`[aria-expanded="false"] ~ .site-nav`), a screen reader announces it.
  No class or variable keeps a second copy that could disagree.
- **DOM order is focus order.** CSS `order` may move things visually, but Tab
  follows the HTML. The Menu button sits straight before the nav it opens,
  and the cart link after it, outside the menu so the count stays visible.
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
- **Tests are plain scripts** run with `python tests/<name>.py`, using only the
  stdlib and the app's own dependencies (Pillow makes the test images),
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
  found, 405 wrong method (with `Allow`), 409 refused by the work's state,
  413 too large.
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
- **Money typed by a person goes through `Decimal`, never `float`.**
  `parse_price()` checks the text against a strict pattern first, then converts
  exactly; `float("19.99") * 100` lands a cent short. Price fields are
  `type="text" inputmode="decimal"`, not `type="number"`.
- **An unticked checkbox sends nothing.** "Ticked" means "the name is present
  in the form", never a comparison with a value.
- **Admin edits to stock are optimistic-concurrency writes.** The form carries
  the stock it loaded; `update_artwork()` saves only
  `WHERE id = ? AND inventory_quantity = ?`, and a mismatch is a 409 with the
  form intact. Stock is guarded because it is the only column something other
  than the admin writes. Since Stage 17 the UPDATE also requires
  `image = ?` (the image this request read), because replacing an image
  deletes the old files: a save that read the row too early must not write
  a deleted image's name back.
- **Status transitions are rules in `ORDER_TRANSITIONS`**, enforced in the
  `WHERE` clause of `change_order_status()`, so a repeat or a disallowed
  change updates zero rows. Stage 14 adds `pending → paid/cancelled`.
- **Destructive actions get a confirmation page** (GET asks, POST acts), not a
  JavaScript `confirm()`. The page predicts refusals; the database enforces
  them (a sold work cannot be deleted: ON DELETE RESTRICT).
- **Form fields use the `form_field` macro** in macros.html (label, value,
  error, hint, aria wiring). Extra attributes go through `kwargs | xmlattr`,
  which escapes them. `checkout.html` still repeats the markup by hand; fold
  it in at Stage 22.
- **Jinja's `do` extension is not loaded.** Build lists in one expression
  instead of appending.
- **Parameterised SQL only** (`WHERE id = ?`). Never f-string user input into
  a query. `tests/test_input.py` parses app.py and fails on any database call
  whose SQL is built by `+`, `%`, `.format()`, or an f-string piece not on its
  reviewed `ALLOWED_IN_SQL` list. Adding a name there is a claim to check.
- **Numbers from a request are ASCII digits.** `is_digits()` (`[0-9]+`), never
  `str.isdigit()`, which is true for "²" (then `int()` crashes) and "٣"
  (then `int()` reads 3). Patterns use `[0-9]`, not `\d`, for the same reason.
  The test fails on any `.isdigit` in app.py.
- **Every text field has a ceiling, written once in Python** (`TEXT_LIMITS`,
  `CHECKOUT_LIMITS`, `MAX_SEARCH_LENGTH`, `MAX_USERNAME_LENGTH`). Templates
  read them through `input_limits` for `maxlength=`: a convenience; the
  server's check is the one that counts. Search text is cut, not refused
  (the box shows what was searched); SQLite errors on a LIKE pattern over
  50,000 bytes. No maximum password length, on purpose. Werkzeug's own
  `MAX_FORM_MEMORY_SIZE` (500KB a field) is the backstop behind ours.
- Prices are stored as **integer cents**, never floats (added Stage 5).
- The data model must support both one-of-a-kind originals and multi-copy
  editions.
- **Image sizes are read from the file, never typed.** `image_size()` reads
  them; the admin form shows them in the image menu and never asks. Any
  `image_width`/`image_height` in a POST is ignored. The allowlist check
  (`image_choices()`) runs before anything opens a file, because a filename
  from a form is a path, and `../../app.py` is a path too.
  `tests/test_images.py` also checks every seeded size against its file.
- **Placeholders are SVG, and only SVG**: files we drew and committed, so
  their contents are trusted. Uploads are never SVG, since an SVG can carry
  a `<script>` that runs as this site.
- **Nothing the browser says about an upload is used.** Filename, extension
  and Content-Type are all chosen by the sender. `prepare_upload()` decodes
  the file with Pillow, restricted to `UPLOAD_FORMATS` (JPEG, PNG, WebP; a
  phone's MPO counts as JPEG), checks the pixel count from the header BEFORE
  decoding (decompression bombs), turns it upright from its EXIF, and keeps
  a copy re-encoded from the pixels. Only the colour profile is carried
  over; EXIF, GPS, comments and trailing bytes are left behind.
- **Uploads are named by us, once.** `secrets.token_hex(16)` plus the
  extension of what the file turned out to be; hex because Windows ignores
  case. Written with mode `"xb"`, so a name is never overwritten and a stored
  path always means the same bytes. `image_file()` is the only code that maps
  a stored path to a file on disk.
- **Size limits are layered.** `MAX_CONTENT_LENGTH` (20 MB) refuses the
  request with a 413 before the body is read; `MAX_IMAGE_SIDE` and
  `MAX_IMAGE_PIXELS` refuse what it would decode to.
- **Validation writes nothing.** The file is written after the whole form
  passes, then the row. A file and a row cannot share a transaction, so if
  the row is not written (an error, or the stock 409) the route deletes the
  file: compensation, as in Stage 14. The worst case is a stray file, never
  a row pointing at a missing one.
- **A rejected form cannot return a file** (browsers refuse to fill in a file
  input), so it says "choose the file again" rather than losing it silently.
- **A form offers its own work's current image, never another work's.**
  `image_choices(current)` takes `current` from the database, not the form.
- **Every upload gets renditions**: WebP copies at `RENDITION_WIDTHS`
  (480/960/1600/2400), only those narrower than the original, named
  `<name>-<width>.webp` beside it. Which exist is derived from the original's
  width, never stored. The set is written all or nothing. When
  `RENDITION_WIDTHS` changes, run `flask --app app rebuild-renditions`.
- **One image, one macro.** Every artwork `<img>` comes from `artwork_image(art,
  slot)` in macros.html, which adds `srcset` (the `srcset` filter) and the
  slot's `sizes`. `sizes` restates the CSS column widths: change a layout in
  style.css, change its slot there. Placeholder SVGs get neither attribute.
- **The lightbox assigns `srcset` before `src`, every time, even when empty**,
  or a placeholder would inherit the previous work's list.
- **Row first, then files, when an image stops being used** -- the mirror of
  creating (files, then row). `remove_image_files()` runs only after the
  UPDATE or DELETE saved; the DELETE uses `RETURNING image` so it removes
  the image of the row actually deleted. The database decides: nothing is
  deleted while any row names the image, and placeholders never are. Files
  are found by globbing `<name>-*.webp`, not from `RENDITION_WIDTHS`, so
  renditions at old widths go too. A file that will not delete is logged,
  and the save still succeeds.
- **`flask --app app sweep-uploads` looks; `--delete` acts.** It removes only
  files named the way this site names them, that no row uses, and that are
  older than `SWEEP_MIN_AGE_SECONDS` -- a younger file may belong to a save
  whose row has not been written yet.
- **Alt text is data, never template wording.** `artworks.alt_text` (written
  in the admin form, optional) and `artists.portrait_alt`; the homepage hero
  is the `HERO` dict beside `GALLERY_NAME`. SQL derives the fallback once
  (`_ALT_CASE`: "<title> by <artist>"; "Portrait of <name>"), so a blank is
  stored as NULL and never rendered as `alt=""`, which would tell a screen
  reader to skip the art. The word "Placeholder" lives in seed.sql, where
  the images really are placeholders; `tests/test_accessibility.py` fails if
  a template or script writes it.
- **The lightbox copies alt text from the card**, like the price line. It
  never rebuilds it. The price line is copied as NODES
  (`replaceChildren(...cloneNode(true).childNodes)`), never through
  `innerHTML`: nothing is parsed, so what was text stays text.
- **Escaping is the defence; headers are the second line.** Jinja escapes
  every `{{ }}` in .html templates, and every attribute is double-quoted.
  Never `|safe`, `Markup()` or `autoescape false`, and no script assigns
  `innerHTML`/`outerHTML` or calls `insertAdjacentHTML`, `document.write`,
  `eval`: `tests/test_output.py` fails on any of them, and parses every page
  with a probe (`"'></title></textarea><x-probe ...>`) in every field.
- **Every response gets `SECURITY_HEADERS`** (one `after_request`): a strict
  CSP (`'self'` only, no `'unsafe-inline'`), `nosniff`, framing limited to
  this site (`frame-ancestors 'self'` + `X-Frame-Options: SAMEORIGIN`; 'self'
  rather than 'none' because the layout audits frame our own pages), and
  `Referrer-Policy: same-origin` (an order URL is its own key). So: no
  inline `<script>`, `<style>`, `style=` or `on...=` anywhere, and no
  `data:` or outside URLs in style.css; the test checks every page. Stage 14
  must add Stripe's checkout host to `form-action` (and whatever else its
  docs require). The test client does not enforce CSP: after changing it,
  check in a browser (violations appear as console errors).
- **Structure is tested without a browser.** `tests/test_accessibility.py`
  parses every page: one `<h1>`, no skipped heading levels, alt on every
  image (`alt=""` only for the lightbox and the captioned admin thumbnail),
  every control labelled, unique ids, ARIA references that resolve.
  Contrast and focus are audited in a browser (all text passes AA; the
  lowest pair, `--ink-soft` on `--paper-warm`, is 5.06:1).
- **Artworks are never cropped.** Show them with `object-fit: contain` inside
  a `.mat`. Photographs of people (artist portraits) may use `cover`.
- **Artwork titles are italic** (`.work-title`), the art-writing convention.
- **Hover effects only on interactive elements.** A hover promises a click.
  Artwork cards became links at Stage 8 and got one then.
- **Visual-only decisions live in CSS**, not Jinja conditionals (for example
  the alternating artist layout uses `:nth-of-type(even)`).
- **Type:** Cormorant Garamond for display sizes only, Inter for text.
  Self-hosted in `static/fonts/` (Stage 19), declared by `@font-face` at the
  top of style.css: three variable-font files, Latin subset, 110KB, with
  their SIL OFL licences beside them. Nothing is fetched from Google. A new
  font version gets a new filename (the upstream version is in the name).
- **A static URL means one exact set of bytes, so it is cached for a year.**
  `url_for('static', ...)` adds `?v=<fingerprint of the content>`
  (`version_static_urls`), and `long_cache_for_static` sends
  `public, max-age=31536000, immutable` when the `?v` matches the file, or
  for write-once names (`fonts/`, `images/artworks/`). Anything else keeps
  Flask's `no-cache`. Editing a file changes its URL; never hard-code a
  `/static/...` path, or it loses the fingerprint.
- **Lazy-load only what starts off screen.** A lazy image waits for layout
  before it is fetched. `artwork_grid(..., eager=N)` loads the first N cards
  at once (All works: one row, 4); the cart's first three lines are eager;
  the hero and the artwork/artist page images are eager with
  `fetchpriority="high"`.
- **Every foreign-key child column is indexed** (`order_items.order_id`,
  `order_items.artwork_id`, `artworks.artist_id`): SQLite checks the child
  table on every parent DELETE. Queries per page are 1-5 and must not grow
  with the collection; `tests/test_performance.py` adds 30 works and checks.

## Open items (as of 2026-09-24, HEAD 928bbef)

**Waiting on the owner:**

- An answer to the question left open since Stage 16: the admin edit form
  guards stock against lost updates but not price -- if two admins save the
  same work at once, one changing the price and the other the title, what
  happens, and why is stock treated differently? Let the owner answer; do not
  answer it for them. (Stage 17 also guards `image`, for a separate reason:
  replacing an image deletes the old files.)
- `/about` still returns the bare string `"Placeholder gallery description."`
  from Stage 1 -- no template, no nav. Owner to choose: a placeholder page
  now, or leave it for Stage 21 with the real text.
- Five stray upload files from Stage 17 testing may still be in
  `static/images/artworks/`; `flask --app app sweep-uploads --delete`
  removes them (owner to run).

**Known gaps, deliberately deferred:**

- Artist portraits' width/height (800x1000) are typed into `index.html` and
  `artist.html`; a real portrait at Stage 21 needs a template change unless
  they move into the `artists` table first.
- The API does not expose alt text (its contract was left unchanged).
- There are no migrations: any schema change needs `python init_db.py
  --reset`, which empties the admins and orders tables. Since Stage 20 a
  stale file is at least refused by name (schema version check).

**Going into Stage 20 (security), already known:**

- No CSRF tokens yet; only `SameSite=Lax`. POST forms live in base.html
  (logout), artwork.html and cart.html (cart), checkout.html, and the admin
  templates (login, artwork form, delete, ship); `/api/cart` takes JSON
  via fetch().
- `SECRET_KEY` falls back to a fixed dev string; the session cookie is not
  `Secure` (development runs on plain http); login has no rate limit.
- Uploads are served by extension from static/ (the extension comes from
  the decoded format, never the upload's name).

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
python tests/test_cms.py
python tests/test_images.py
python tests/test_uploads.py
python tests/test_cleanup.py
python tests/test_navigation.py
python tests/test_layout.py
python tests/test_accessibility.py
python tests/test_performance.py
python tests/test_input.py
python tests/test_output.py
```

Make any missing image renditions (after changing `RENDITION_WIDTHS`, or for
images uploaded before Stage 17 part 3). Safe to run repeatedly:

```powershell
flask --app app rebuild-renditions
```

List uploaded files no artwork uses (left by a crash, or a file that was
locked when its work changed), then remove them once you have looked:

```powershell
flask --app app sweep-uploads
flask --app app sweep-uploads --delete
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
│                  #   checkout, order, orders, 404, 413, macros;
│                  #   admin/ holds login, dashboard, artwork_form,
│                  #   artwork_delete, orders
├── static/           # css/style.css, js/{lightbox,filter,cart,nav}.js,
│                  #   fonts/ (woff2 + OFL licences),
│                  #   images/placeholders (SVG, committed),
│                  #   images/artworks (uploads, gitignored)
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
- [x] **16 — Admin / CMS.** Add/edit/delete artwork, pricing, availability,
      featured flag. Simple auth. Split in two, like Stage 10.
      **Part 1:** `admins` table with hashed passwords, `flask create-admin`,
      login/logout, `@admin_required`, safe `next=`, dashboard.
      **Part 2:** create/edit/delete artworks with server-side validation,
      optimistic concurrency on stock, delete refused for sold works, and
      `paid → shipped` via `ORDER_TRANSITIONS`.
- [x] **17 — Image management.** Static file organisation, naming conventions,
      optimisation, safe upload concepts. Split in four.
      **Part 1 (done):** sizes read from the file (`image_size()`), not typed;
      the form cannot override them; placeholders restricted to SVG.
      **Part 2 (done):** safe uploads with Pillow: multipart forms, a 413
      limit, decode-to-verify with an allowlist of formats, pixel limits,
      EXIF orientation, re-encode without metadata, generated names written
      once, the file deleted if its row is not saved.
      **Part 3 (done):** WebP renditions at four widths, `srcset`/`sizes`
      through one `artwork_image` macro, the lightbox too, and
      `flask rebuild-renditions`.
      **Part 4 (done):** a replaced or deleted work's files are removed
      after the row change saves (row first, then files), only when no row
      uses them; the image joins stock in the UPDATE guard; `DELETE ...
      RETURNING`; `flask sweep-uploads` for strays, looking before deleting.
- [x] **18 — Responsive polish.** Media queries, responsive type and grids,
      mobile navigation, tested across breakpoints. Split in two, after a
      measured audit of every page at 320-1440px.
      **Part 1 (done):** the phone menu (Menu button + visible cart, switched
      on by nav.js, links visible without JS), a content-derived 64em
      breakpoint that also closed a two-row header gap at 800-1000px.
      **Part 2 (done):** the admin pages' overflow at 320px, traced to its
      causes (visually-hidden text escaping an unpositioned scroll box; the
      fieldset min-content default), a pinned first table column, 24px
      breadcrumbs, admin checkboxes and admin bar, 11px minimum text, the
      800px block moved to 50em. Re-audited: no page overflows at any
      width. `tests/test_layout.py` pins the invisible one-line fixes.
      Found, not in scope: `/about` still returns bare text from Stage 1.
- [x] **19 — Performance & accessibility.** Lazy loading, alt text, keyboard
      navigation, contrast, query efficiency. Audited first (15 pages):
      structure, labels, ids, ARIA and contrast all passed already; queries
      1-5 per page with no per-row loops. Split in two.
      **Part 1 (done):** alt text as data (`alt_text`, `portrait_alt`,
      `HERO`, SQL fallback, admin field), the lightbox copying it, a focus
      style for the admin checkboxes, `tests/test_accessibility.py`.
      **Part 2 (done):** fingerprinted static URLs cached for a year
      (a second page now makes no request for CSS, JS or fonts);
      self-hosted variable fonts; an index on `order_items.artwork_id`;
      eager loading for what is on screen at first.
      `tests/test_performance.py` checks all four, and that queries per
      page do not grow with the collection.
      Found, not in scope: artist portraits' width/height are still typed
      into two templates (800x1000), so a real portrait at Stage 21 would
      need a template change; the API does not expose alt text.
- [~] **20 — Security basics.** Input validation, SQL injection, output
      escaping, sessions, CSRF, protecting admin, payment architecture.
      Audited first by attacking a throwaway copy (11 findings; the worst: a
      cookie signed with the committed fallback key opens /admin). Split in
      five.
      **Part 1 (done):** ASCII-only numbers (`is_digits`; "²" was a 500),
      length limits on checkout and login, search cut to 100 characters (a
      60KB search was a public 500), `tests/test_input.py` (numbers, lengths,
      injection strings, and a parse of every query in app.py). Plus a
      schema version check, after the owner's database (built before Stage
      19) failed with "no such column".
      **Part 2 (done):** `tests/test_output.py` (a breakout probe in every
      field, 17 pages parsed; escape hatches; headers on every kind of
      response; nothing inline), the lightbox copying nodes instead of
      `innerHTML`, and `SECURITY_HEADERS`. Checked in a browser: no CSP
      violations on any page, lightbox and fetch() still work, an injected
      inline script/handler/style is refused, and a page on another port
      cannot frame /admin.
      **Part 3:** sessions: no public fallback key, production cookie
      settings, admin sessions that expire and can be revoked.
      **Part 4:** CSRF tokens on every POST and on `/api/cart`.
      **Part 5:** login throttling, trusted hosts, the mock payment off
      outside development, payment security design for Stage 14.
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
