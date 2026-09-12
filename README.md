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
- [ ] Stage 2 — homepage with templates and CSS
