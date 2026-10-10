# Art Gallery

A full-stack digital gallery and art marketplace for the work of Jean Jansem
and Jean Carzou, built from scratch as a learning project: vanilla HTML, CSS
and JavaScript on the front end, Python and Flask on the back end, SQLite
with raw SQL for storage. No framework and no ORM, so every layer is visible.

The site was built on **placeholder content** ("Artist One", "Artwork
Title", placeholder images) so the architecture could be finished first.
Real content is being added now (Stage 21), with every fact cited to a
source. Images of the artists' works stay placeholders until reproduction
rights are cleared.

## What it does

- Gallery pages: a homepage, artist pages, All works with search, filters
  and sorting in SQL, artwork pages, and a keyboard-accessible lightbox.
- A shopping cart in the signed session cookie, and a checkout that claims
  stock inside one database transaction. Payment is a clearly labelled
  **mock** for now; real payments (Stripe) are a later stage.
- A JSON API (`/api/artworks`, `/api/cart`) that the cart's JavaScript uses,
  with the plain form as the fallback.
- An admin for artworks and orders, with hashed passwords, revocable
  sessions, login throttling, and safe image uploads (decoded and re-encoded
  with Pillow, with responsive WebP renditions).
- Security basics throughout: parameterised SQL, escaping and a strict
  Content Security Policy, CSRF tokens on every POST, trusted hosts.

## Stack

- Frontend: HTML, CSS, JavaScript (no framework), self-hosted fonts
- Backend: Python 3.13, Flask
- Database: SQLite, raw SQL
- Images: Pillow

## Setting up (Windows / PowerShell)

```powershell
git clone https://github.com/ariavedikian/art-gallery.git
cd art-gallery
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python init_db.py
```

If PowerShell refuses to run the activate script, allow local scripts once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Running it

```powershell
python app.py
```

Then open http://127.0.0.1:5000. Stop the server with Ctrl+C. The first run
creates `instance/secret_key`, which signs the session cookie; it is
gitignored and never shared.

To use `/admin`, create an admin first (it asks for the password without
showing it):

```powershell
flask --app app create-admin yourname
```

## Database

The SQLite database is generated from SQL files, so it can be rebuilt at any
time. `--reset` deletes it first, including admins and orders:

```powershell
python init_db.py --reset
```

`database/schema.sql` defines the tables; `database/seed.sql` fills them with
the site's real content, every fact cited to a source (listed on the artist
and artwork pages). The tests use their own placeholder data,
`tests/seed.sql`. The generated `database/art_gallery.db` is gitignored.

## Tests

Plain Python scripts, no test framework. Each builds a throwaway database,
never touches yours, and exits non-zero on failure. Run one:

```powershell
python tests/test_api.py
```

or all of them:

```powershell
Get-ChildItem tests\test_*.py | ForEach-Object { python $_.FullName }
```

## Running in production

`python app.py` is the development server and refuses to start in
production. Under a production WSGI server, set:

- `ART_GALLERY_ENV=production`
- `ART_GALLERY_SECRET_KEY`: at least 32 characters, for example from
  `python -c "import secrets; print(secrets.token_hex(32))"`
- `ART_GALLERY_HOSTS`: the site's domain names, comma-separated
- `ART_GALLERY_PROXIES`: how many proxies are in front, if any

In production, checkout is closed until real payments are added.

## Project layout

```
art-gallery/
├── app.py            # the Flask application: routes, data access, rules
├── init_db.py        # rebuilds the database from the SQL files
├── requirements.txt  # exact Python packages, pinned
├── templates/        # Jinja templates (admin/ for the admin pages)
├── static/           # css, js, fonts, placeholder images;
│                     #   images/artworks/ holds uploads (gitignored)
├── database/         # schema.sql, seed.sql, art_gallery.db (generated)
└── tests/            # test scripts, support.py helpers, seed.sql fixture
```

## Progress

Built in numbered stages, each finished and reviewed before the next.

- [x] Stages 1–4: Flask basics, templates and CSS, gallery design, artist pages
- [x] Stages 5–8: SQLite schema, Flask + SQLite, a database-driven gallery,
      artwork pages and a 404
- [x] Stage 9: JavaScript lightbox
- [x] Stage 10: search and filtering, in the browser then in SQL
- [x] Stages 11–13: shopping cart, checkout with a transaction, orders
- [ ] Stage 14: real payments with Stripe (deferred)
- [x] Stage 15: JSON API
- [x] Stage 16: admin / CMS
- [x] Stage 17: image uploads, renditions and cleanup
- [x] Stage 18: responsive layout and a phone menu
- [x] Stage 19: performance and accessibility
- [x] Stage 20: security
- [ ] Stage 21: real content, every fact cited (in progress)
- [ ] Stage 22: final refactor
