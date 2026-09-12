"""
Art Gallery — a Flask web application.

Stage 1: the smallest possible working web server.
Right now this file IS the whole backend. As the project grows it will gain
templates (Stage 2+), a database (Stage 5+), and a cart/checkout (Stage 11+).
"""

from flask import Flask

# `Flask(__name__)` creates the application object.
# __name__ is a built-in Python variable holding this module's name ("app").
# Flask uses it to figure out where this file lives on disk, so it knows where
# to look for the `templates/` and `static/` folders later.
app = Flask(__name__)


# A "route" maps a URL path to a Python function.
# When a browser asks for "/", Flask runs home() and sends back what it returns.
@app.route("/")
def home():
    return "Art Gallery"


@app.route("/about")
def about():
    # Placeholder copy. Real gallery content comes much later (Stage 21).
    return "Placeholder gallery description."


@app.route("/health")
def health():
    # Returning a dict makes Flask send JSON instead of HTML.
    # Useful for checking the server is alive without opening a browser.
    return {"status": "ok", "stage": 1}


# This block only runs when you execute `python app.py` directly.
# debug=True gives auto-reload on file save and a detailed error page.
# It is a DEVELOPMENT setting only — never use it on a public server.
if __name__ == "__main__":
    app.run(debug=True, port=5000)
