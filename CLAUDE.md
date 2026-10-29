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
- **Two seeds, two questions.** `database/seed.sql` is what the site shows,
  and changes with the content. `tests/seed.sql` is the tests' fixture:
  placeholders only, forever, and the only file a test may take an expected
  VALUE from. A test checking a RULE every seed must obey (image sizes now,
  citations from Stage 21 Part 3) runs over both: `temp_database(SITE_SEED)`.
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
- **An unknown fact is NULL, and the page shows nothing for it.** Facts a
  real record may lack are nullable (artists: `lifespan`, `summary`, `bio`;
  artworks: `year`, `medium`, `description`, `dimensions`, `edition`,
  `inscriptions`); a blank admin field is stored as NULL, never `''`.
  Three layers: `app.jinja_env.finalize` prints None as nothing (it once
  printed "None", and `data-year="None"` reached the lightbox); a labelled
  fact goes through the `detail(label, value)` macro, which leaves out the
  whole row; a list of facts is `[a, b] | select | join(", ")`, so a
  missing one takes its comma with it (`filter(Boolean)` in lightbox.js).
  `tests/test_unknown_facts.py` blanks every optional fact and parses each
  page for "None", empty `<p>`/`<dd>`/`<dt>`, and stranded separators.
- **Every fact is cited.** `sources` (a `ref` the seed uses to point at
  it, the citation, an http(s) `url` and the date it was `accessed`) and two
  junction tables, `artist_citations` and `artwork_citations`, one row per
  (subject, field, source), with an optional `locator` ("p. 112"). Citable
  fields are `ARTIST_FIELDS` / `ARTWORK_FIELDS` in app.py and the CHECK
  lists in schema.sql (stated twice; the test compares them); `artist` is
  the attribution. Not cited: alt text, category, price, stock, running
  order. Citations cascade with their subject; a cited source cannot be
  deleted. The artist and artwork pages end with a numbered Sources list
  (`sources_list` macro), one entry per source with the facts it supports.
  `tests/test_content.py` checks `database/seed.sql`: every non-NULL fact
  cited, no placeholder text or picture, every source used, `http://` or
  `https://` (nothing else may reach an href) and dated, portraits
  800x1000, its pages load and list their sources; and that
  `tests/seed.sql` holds no real name. It compares text with
  `markupsafe.escape`, Jinja's own function: Jinja writes every `"` as
  `&#34;`, and `html.escape(quote=False)` does not.
- **How a fact earns its place** (Stage 21 Part 4). Authority records (the
  BnF's) and institutions speaking of their own business (the Académie on
  its member, a museum on its collection) come first; two independent
  sources beat one; in a conflict, the source closest to the fact wins
  (the museum that received a gift, over a news report of it). Dealer
  listings, auction databases, Wikipedia and search summaries are never
  sources: a search summary gave Carzou's birthplace as Paris, and the BnF
  record it summarised says Aleppo. A fact is checked against the world as
  well as its sources: "Arts et Lettres, 1953" fell because the order was
  created in 1957. Candidates go to the owner in a numbered table; text is
  written only from approved facts, sentence by sentence, and approved
  again before it goes into the seed.
- **The neutral picture says what is true.** `NO_IMAGE`
  (`placeholders/no-image.svg`, 800x1000, "Image not available") stands in
  wherever an image may not be shown (reproduction rights). Its alt text is
  derived in SQL (`_ALT_CASE`, `_ARTIST_COLUMNS`) and beats anything written
  for the row: the fallbacks would call a grey box "Portrait of ...". It is
  the one file in `placeholders/` the real seed may use.
- **Stock is not an edition.** `inventory_quantity` is how many copies the
  gallery has ("Available: 12 copies"); `edition` is which impression a
  print is ("23/150"). The artwork page used to label stock "Edition".
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
- **Configuration comes from two environment variables, read by
  `configure()`.** `ART_GALLERY_ENV` is `development` (the default) or
  `production`; anything else refuses to start (a typo must not mean
  development). `ART_GALLERY_SECRET_KEY` signs the session cookie: at least
  32 characters, required in production. In development without it, a key
  is generated once into `instance/secret_key` (gitignored, `O_EXCL`, 0600),
  so no key is ever committed or shared. Production adds a `Secure` cookie
  named `__Host-session` (only this host, only HTTPS, no subdomain can set
  it) and HSTS. Deleting `instance/secret_key` logs everyone out and empties
  every cart. The tests set their own random key and development, in
  support.py, so they never touch `instance/`.
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
- **Tests build their own throwaway database** from `database/schema.sql`
  and `tests/seed.sql` in a temp folder and point `app.DATABASE_PATH` at it,
  via `tests/support.py`. A test that can destroy the database you are
  working on is worse than no test.
- **A page sweep checks it got the page.** Tests that loop over many pages
  fetch them with `support.get_page()`, which fails unless each answers 200
  (404 only for `/no-such-page`). Without it, a renamed slug served the 404
  page, which passed every general check while printing PASS beside the
  artist page's address (found proving Stage 21 Part 1).
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
  found, 403 no CSRF token, 405 wrong method (with `Allow`), 409 refused by
  the work's state, 413 too large.
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
- **The cookie claims a login; the database decides.** The session holds
  `{"id", "key", "at"}`. `current_admin()` honours it only if the admin
  still exists, `key` matches `admins.session_key` (`compare_digest`), and
  it is under `ADMIN_SESSION_SECONDS` (12h, from login, not idle time).
  Anything else, malformed included, is removed from the cookie. A cookie
  session cannot be deleted on the server, only made to stop matching:
  logout and a new password replace `session_key`, which ends every copy
  on every device. The key is also a second barrier behind the secret key:
  a forger with the signing key still cannot guess it.
- **One message for every failed login**, and a dummy hash check for unknown
  usernames, so neither the wording nor the timing reveals which exist.
- **Failed logins are throttled**, counted in `login_failures` per IP
  (`LOGIN_LIMIT_PER_IP`, 10) and per username (`LOGIN_LIMIT_PER_USERNAME`,
  50) over `LOGIN_WINDOW_SECONDS` (15 min). Past either limit the form is a
  429 with `Retry-After`, answered BEFORE the password is checked (a right
  password is refused too, so a refused guess learns nothing), and the
  refusal is not recorded (a flood cannot grow the table). Unknown usernames
  are counted the same way. The username limit is looser because anyone
  can spend it; `flask create-admin` (a new password) clears it. Check and
  insert are separate statements: two simultaneous guesses may overshoot
  by one, which is harmless, unlike stock.
- **The client's address is `request.remote_addr`**, which ignores
  `X-Forwarded-For` unless `ART_GALLERY_PROXIES` says how many proxies are
  in front (then `ProxyFix`). Otherwise anyone could pick an address and
  dodge the throttle. `configure()` wraps `_plain_wsgi_app`, never an earlier
  wrapping, so it can run repeatedly.
- **Only the site's own host names are answered** (`TRUSTED_HOSTS`, from
  `ART_GALLERY_HOSTS`, required in production; localhost and 127.0.0.1 in
  development). Any other Host header is a 400 before our code runs, so
  `url_for(..., _external=True)` can never build a link to someone else's
  domain. Add a LAN IP to `ART_GALLERY_HOSTS` to test on a phone.
- **No mock payment in production** (`MOCK_PAYMENTS`). Checkout answers 503
  "Purchases open soon" (`checkout_closed.html`), and `place_order()`
  refuses on its own as a second lock. `python app.py` (the debug server,
  whose traceback page is a Python console) refuses to start in production.
- **`next=` is honoured only if it is a path on this site** (`safe_next()`):
  no scheme, no host, not `//`, no backslash. Otherwise, an open redirect.
- **Logout is a POST**, ends every session of that admin (above), and only
  removes the admin key from this cookie; the visitor's cart and
  remembered orders belong to the browser, not the login.
- **Admin responses are `Cache-Control: no-store`**, and admin pages carry
  `noindex`. The public site never links to `/admin`.
- **The session cookie is `SameSite=Lax`**, set explicitly rather than trusted
  to browser defaults. It is the browser's rule and ignores ports and
  sibling subdomains ("same site"); the CSRF token below is our own check.
- **Every POST carries this session's CSRF token.** `check_csrf` is a
  `before_request` for every method outside `SAFE_METHODS`, so a new route
  is protected without remembering to. The token (one per session, made by
  the `csrf_token()` Jinja global) travels in the `csrf_token` hidden field
  (`csrf_field()` in macros.html, in every `method="post"` form and never
  a GET form) or the `X-CSRF-Token` header (cart.js reads it from the form
  it enhances). Compared as bytes with `compare_digest` (a non-ASCII str
  would raise). A refusal is a 403 (`csrf.html`, or JSON under /api/) and
  is logged. In tests, `support.PageClient` sends the token the way a page
  would; `csrf=False` sends a request as another site would.
  `tests/test_csrf.py` walks every POST route: refused without the token
  and unchanged, accepted with it.
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
  `tests/test_images.py` also checks every seeded size against its file,
  in both seeds.
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
  reader to skip the art. The word "Placeholder" lives in the seed data, where
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
  `order_items.artwork_id`, `artworks.artist_id`, both citation tables'
  `source_id`; their subject ids lead their primary keys): SQLite checks the child
  table on every parent DELETE. Queries per page are 1-5 and must not grow
  with the collection; `tests/test_performance.py` adds 30 works and checks.

## Open items (as of 2026-10-09, Stage 21 Part 1)

**Waiting on the owner:**

- An answer to the question left open since Stage 16: the admin edit form
  guards stock against lost updates but not price -- if two admins save the
  same work at once, one changing the price and the other the title, what
  happens, and why is stock treated differently? Let the owner answer; do not
  answer it for them. (Stage 17 also guards `image`, for a separate reason:
  replacing an image deletes the old files.)
- `/about` still returns the bare string `"Placeholder gallery description."`
  from Stage 1 -- no template, no nav. Decided: it becomes a real page with
  the owner's text in Stage 21 Part 6.
- Five stray upload files from Stage 17 testing are still in
  `static/images/artworks/` (one PNG, `36450e54...png`, and its four
  renditions; confirmed by `sweep-uploads` on 2026-10-09);
  `flask --app app sweep-uploads --delete` removes them (owner to run).

**Stage 21 decisions (2026-10-09; the owner chose each recommendation):**

- *Real content lives in files.* `database/seed.sql` holds only real, cited
  content (from Part 3); the tests have `tests/seed.sql` (Part 1, done).
  Catalogue facts are edited in the seed, not the admin, while there is no
  migration path; export or migrations wait for deployment.
- *Sources are recorded per fact*, in a `sources` table and citation tables
  naming the field each source supports (Part 3). A test fails on any fact
  in `database/seed.sql` without a citation. Sources are shown on the
  artist and artwork pages. Facts are written in our own words from
  approved sources, never pasted; dealer listings and search summaries are
  not sources.
- *Text now, images only after permission.* The ADAGP directory (checked
  2026-10-09) lists Jean Jansem (1920-2013) and Jean Carzou (1907-2000) and
  says ADAGP manages their reproduction and representation rights; every
  reproduction must carry "© Adagp, Paris, <year>". Owning a work does not
  include the right to reproduce it (CPI art. L111-3). Real works show a
  neutral "image not available" picture until the owner has ADAGP's written
  authorisation (Part 7). Artist portraits are the photographers' rights,
  a separate question.
- *New optional catalogue fields:* `dimensions`, `edition`, `inscriptions`
  (Part 2), each citable. The artwork page's "Edition: N available" is
  really stock and gets an honest label.
- *Works shown are works the owner holds.* Placeholder works never appear
  under a real artist's name (that would be an invented attribution), so
  the real artists start with zero works; the site handles that already.

**Stage 21, still open:**

- `dimensions`, `edition` and `inscriptions` are not in the admin form, on
  purpose: cited facts are edited in `database/seed.sql`. The form still
  edits title, date, medium and description, and an edit there leaves the
  old citation pointing at the new value: whether the admin should edit
  facts at all is a question for Part 5. Nor are the new fields or the
  sources in the API: its contract was left unchanged.
- The site now shows real artists (names, dates, summaries, biographies)
  beside placeholder gallery text, hero and name (`GALLERY_NAME`, `HERO`,
  the homepage paragraphs, the footer): Part 6.
- A biography is one `<p>` (Jansem's is 165 words). Paragraph breaks would
  need the template to split `bio` on blank lines; not done.
- Titles inside a biography (*Yeghern*, *Les Indes galantes*) are plain
  text, not italic: the text is escaped, so it cannot carry markup. The header still fits one row
  at 64em with the real names (823px of ~976px, measured 2026-10-09); the
  wordmark is "Gallery Placeholder", so re-measure when it changes.
- *Things placeholders hid:* portraits' 800x1000 is typed into
  `index.html` and `artist.html` (see Known gaps); `GALLERY_NAME` and
  `HERO` in app.py; real alt text for every real image; the header's 64em
  breakpoint was measured with the placeholder names, so re-measure if the
  gallery name changes. Checkout is closed in production until Stage 14.
- *The owner may supply photos of works they own.* Treat them as photos to
  research, not as identified works: transcribe what is visible (signature,
  edition number, inscriptions, labels on the back), search for matching
  records, and present candidates with their evidence for the owner to
  confirm. Never assign a title, date or edition that was not confirmed.

**Known gaps, deliberately deferred:**

- Artist portraits' width/height (800x1000) are typed into `index.html` and
  `artist.html`; a real portrait at Stage 21 needs a template change unless
  they move into the `artists` table first.
- The API does not expose alt text (its contract was left unchanged).
- There are no migrations: any schema change needs `python init_db.py
  --reset`, which empties the admins and orders tables. Since Stage 20 a
  stale file is at least refused by name (schema version check).

**Left after Stage 20, deliberately (not bugs, not yet worth building):**

- No second factor for the admin login, and no record of which admin
  changed what. Both matter once there is more than one admin.
- Dependencies are pinned but not checked for known vulnerabilities; a
  `pip-audit` run before deploying would do it.
- Uploads are served by extension from static/ (the extension comes from
  the decoded format, never the upload's name), with `nosniff`.
- The throttle can lock the real admin out if an attacker sustains 50+
  failures every 15 minutes against the username; `flask create-admin`
  (new password) is the way back in.

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

**Security design, worked out in Stage 20** (what the Stage 20 code already
does, and what `payments.py` must respect; check the details against
Stripe's current docs, which are the authority on their side):

- *Card data never touches this site.* Use Stripe's hosted Checkout page (a
  redirect), not a card form of our own. Card numbers are then typed only
  into Stripe's page, which keeps the site out of the card-handling rules
  almost entirely, and needs no Stripe script in our pages -- so the CSP
  stays as it is, except the next point.
- *CSP:* the checkout POST will redirect the browser to Stripe. Chrome
  applies `form-action` to where a form submission is redirected, so add
  Stripe's checkout host to `form-action` in `CONTENT_SECURITY_POLICY`, and
  watch the browser console for any other violation the first time.
- *Amounts come from our database only.* Build Stripe's line items from
  `get_cart_lines()` -- prices read fresh from SQL -- never from anything in
  the request. The same rule as the cart since Stage 11.
- *The return address is built from the Host header* (`url_for(...,
  _external=True)` for success and cancel URLs). `TRUSTED_HOSTS` (Part 5)
  is what stops a forged Host from sending a buyer to another domain, and
  `ART_GALLERY_PROXIES` makes the scheme https behind a proxy.
- *The webhook cannot carry our CSRF token* -- Stripe is not one of our
  pages. Its protection is Stripe's signature instead: verify the
  `Stripe-Signature` header against the raw body (`request.get_data()`,
  before any parsing) with the endpoint's signing secret, and refuse
  anything that fails. That needs an explicit exemption in `check_csrf`
  (a `CSRF_EXEMPT` set holding that one endpoint), and `tests/test_csrf.py`
  must then check that the exempt set is exactly that endpoint, and that
  the endpoint refuses a bad signature. Never a blanket `/webhooks/` rule.
- *Before marking an order paid, check the event matches it:* the order
  reference, the amount and the currency, against our own row.
- *Duplicates are harmless by construction*: the status-guarded UPDATE
  above changes 0 rows the second time. Answer 2xx anyway, or Stripe
  retries.
- *Keys live in the environment* (`.env` is gitignored), are refused in
  code unless they are test keys (`sk_test_`), and are never logged or put
  in a template. Nor are full webhook payloads logged: they hold the
  buyer's name and address.
- *`MOCK_PAYMENTS` stays for development.* payments.py replaces the mock
  step inside the order flow; keep `place_order()`'s refusal in production
  for the mock path.

## Running it

```powershell
cd "C:\Users\ariav\ICS\Claude Projects\art-gallery"
.\venv\Scripts\Activate.ps1
python app.py          # http://127.0.0.1:5000
```

The first run creates `instance/secret_key` (gitignored). On a real server
set, instead:

- `ART_GALLERY_ENV=production`
- `ART_GALLERY_SECRET_KEY` (make one with
  `python -c "import secrets; print(secrets.token_hex(32))"`)
- `ART_GALLERY_HOSTS` (the domain names, comma-separated)
- `ART_GALLERY_PROXIES` (how many proxies are in front, if any)

and run it under a production WSGI server, never `python app.py`, which
refuses to start in production.

The repository is on GitHub, private: `origin` is
https://github.com/ariavedikian/art-gallery (pushed 2026-10-09, replacing
the README GitHub generated). Every commit carries the owner's email, so
think before making it public.

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
python tests/test_sessions.py
python tests/test_csrf.py
python tests/test_protection.py
python tests/test_unknown_facts.py
python tests/test_content.py
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
│                  #   checkout, checkout_closed, order, orders, 404,
│                  #   413, csrf, macros;
│                  #   admin/ holds login, dashboard, artwork_form,
│                  #   artwork_delete, orders
├── static/           # css/style.css, js/{lightbox,filter,cart,nav}.js,
│                  #   fonts/ (woff2 + OFL licences),
│                  #   images/placeholders (SVG, committed),
│                  #   images/artworks (uploads, gitignored)
├── init_db.py        # rebuilds the database from SQL files
├── tests/            # plain runnable scripts, stdlib only (no pytest yet);
│                  #   support.py holds the throwaway-database helpers,
│                  #   seed.sql the tests' placeholder data (the fixture)
└── database/         # schema.sql (artists, artworks, sources,
                  #   artist_citations, artwork_citations, orders,
                  #   order_items, admins, login_failures),
                  #   seed.sql (the site's content), art_gallery.db (generated)
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
- [x] **20 — Security basics.** Input validation, SQL injection, output
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
      **Part 3 (done):** `configure()` and `ART_GALLERY_ENV`; no committed
      key (generated `instance/secret_key`, or the environment's, required
      in production); production cookies `Secure` + `__Host-` + HSTS;
      revocable admin sessions (`admins.session_key`, schema version 2)
      with a 12-hour limit. `tests/test_sessions.py` replays the audit's
      forged-cookie and copied-cookie attacks.
      **Part 4 (done):** a CSRF token on every POST: `check_csrf` before
      every request, `csrf_field()` in all nine forms, the header from
      cart.js, a 403 page. `tests/test_csrf.py` sends each of the 11 POST
      routes a request that would succeed, without and then with the
      token. In a browser, a form on another port posted to /cart/add WITH
      the gallery's cookie (same site to SameSite) and only the token
      refused it.
      **Part 5 (done):** login throttling per IP and per username
      (`login_failures`, schema version 3), `TRUSTED_HOSTS`, `ProxyFix`
      only when declared, no mock payment in production (route and
      `place_order()`), the debug server refused in production, and the
      payment security design for Stage 14 (below).
      `tests/test_protection.py`. Checked in a browser against a
      production-mode server: the `__Host-` Secure cookie works on
      http://localhost (Chrome counts it as secure), checkout is 503,
      127.0.0.1 is refused as an untrusted host, and the 11th login shows
      the throttle message.
- [~] **21 — Real content.** Artist One → Jean Jansem, Artist Two → Jean
      Carzou. Verified sources only. Architecture should not change.
      Audited first (decisions and findings in Open items). Split in seven.
      **Part 1 (done):** the tests' own placeholder seed (`tests/seed.sql`),
      rule checks run over both seeds, `support.get_page()` for page
      sweeps. Proved on throwaway copies: a content edit to
      `database/seed.sql` broke 3 test files before and none after; the
      same edit to `tests/seed.sql` breaks 6.
      **Part 2 (done):** room for the unknown (schema v4): `summary`, `bio`,
      `medium`, `description` nullable; `dimensions`, `edition`,
      `inscriptions` added; unknowns shown as nothing (`finalize`, the
      `detail` macro, `select | join`, the lightbox caption); stock
      labelled "Available: N copies". `tests/test_unknown_facts.py`, written
      first: 18 failures on the old code; each fix removed in a throwaway
      copy is caught (no `finalize`: `data-year="None"` on four pages; a
      `detail` that always writes its row: empty `<dd>`s). Checked in a
      browser: the lightbox caption and hidden description, no CSP errors,
      no overflow at 320px with the longer labels.
      **Part 3 (done):** `sources` and the two citation tables (schema v5),
      a Sources list on the artist and artwork pages, `NO_IMAGE` with its
      alt text derived in SQL, `tests/test_content.py`. `database/seed.sql`
      is now real: Jean Jansem (1920–2013) and Jean Carzou (1907–2000),
      names and dates cited to their ADAGP directory entries, portraits the
      neutral picture, no works. The test seed gained one placeholder source,
      so every page sweep sees a Sources list. Six rules broken in throwaway
      copies, each caught by name (an uncited summary, a placeholder
      portrait, an http source with no date, a real name in the test seed,
      the neutral picture described as a portrait, a schema CHECK list that
      disagrees with app.py). `test_images.py` now says when a seed has no
      works to check, instead of passing silently. In a browser: the header
      still fits one row at 64em, Sources render, no console errors.
      **Part 4 (done):** artist research. 28 candidate facts from the BnF,
      the Académie des beaux-arts, Paris Musées, the Musée Arménien de
      France, the Armenian Genocide Museum-Institute, the Azumino Jansem
      Museum and Armenpress; the owner approved them by number and the
      wording sentence by sentence. Both artists now have a summary and a
      biography (11 sources, 22 citations). Left out: Jansem's Arts et
      Lettres (no reliable source; 1953 predates the order), his place of
      death and exact birth village (sources disagree), Carzou's day of
      birth (1 January, a likely stand-in). Sources may be `http://` (the
      Azumino museum has no https).
      **Part 5 (in progress):** the owner's works. 19 framed works on
      paper (10 Carzou, 9 Jansem); the owner's photos are in `/artworks/`
      (gitignored: research material, never published). The file names
      are the owner's own labels, not evidence. Pencil inscriptions were
      transcribed from enlarged crops, then matched to the owner's printed
      description sheets (`artworks/title-info/`, FR/EN/HY). Two new kinds
      of source, without URLs: `works-themselves` (what is written on each
      sheet: wins any disagreement about its own inscriptions) and
      `owner-description-sheets` (title, year, medium, size; cm only, as
      one English size is plainly wrong). Titles are the French title with
      the English in brackets. Seven editions are NULL where the sheet and
      the pencil number disagree or the pencil is illegible; the
      dedication on *Les soliloques du pauvre* is not recorded (owner's
      wish). All 19 are not for sale (price 0), unfeatured, NO_IMAGE,
      until the owner decides. Still to settle: the seven edition numbers,
      prices and which works are for sale, which are featured, and whether
      the admin should edit cited facts at all.
      **Part 6:** the gallery's own words: name, hero, homepage text, footer,
      a real `/about` page; re-measure the header if the name changes.
      **Part 7:** real images, only after ADAGP's written authorisation:
      the credit line, real alt text, portrait sizes out of the templates.
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
