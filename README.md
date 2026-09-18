# Art Gallery

A full-stack digital gallery and art marketplace, built from scratch with
HTML / CSS / JavaScript on the front end, Python + Flask on the back end,
and SQLite for storage.

Development uses **placeholder content** ("Artist One", "Artwork Title", ...).
Real artist and artwork data is added only once the architecture is stable.

## Stack

- Frontend: HTML, CSS, JavaScript (no framework)
- Backend: Python 3.13, Flask
- Database: SQLite (added in Stage 5)

## Running it locally (Windows / PowerShell)

```powershell
cd "C:\Users\ariav\ICS\Claude Projects\art-gallery"
.\venv\Scripts\Activate.ps1
python app.py
```

Then open http://127.0.0.1:5000 in a browser. Stop the server with Ctrl+C.

If PowerShell refuses to run the activate script, allow local scripts once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Database

The SQLite database is generated from SQL files, so it can be rebuilt at any
time:

```powershell
python init_db.py --reset
```

`database/schema.sql` defines the tables; `database/seed.sql` fills them with
placeholder content. The generated `database/art_gallery.db` is gitignored.

Inspect it from Python:

```powershell
python -c "import sqlite3; print(sqlite3.connect('database/art_gallery.db').execute('SELECT name FROM artists').fetchall())"
```

## Project layout

```
art-gallery/
├── app.py            # the Flask application (routes live here)
├── requirements.txt  # exact Python packages this project needs
├── venv/             # local Python environment (not committed)
├── templates/        # HTML templates            (Stage 2)
├── static/           # css / js / images          (Stage 2)
└── database/         # schema.sql + SQLite file   (Stage 5)
```

## Progress

- [x] Stage 1 — environment, Flask basics, first routes
- [x] Stage 2 — homepage with templates and CSS
- [x] Stage 3 — gallery landing page design
- [x] Stage 4 — artist pages and dynamic routes
- [x] Stage 5 — SQLite schema and placeholder data
- [ ] Stage 6 — connect Flask to SQLite
