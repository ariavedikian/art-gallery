"""
Can a session cookie be forged, outlive its login, or be used by a copy?

Run it:

    python tests/test_sessions.py

Two of these checks are attacks that WORKED in the Stage 20 audit:

  forged   a cookie signed with the old committed fallback key opened /admin
  copied   a cookie copied before logout still opened /admin afterwards

The rest check the pieces behind the fixes: where the signing key comes from,
the production cookie settings, and the three things current_admin() now
insists on -- the admin exists, the key matches, the login is under 12 hours.
"""

import os
import sys
import time
from types import SimpleNamespace

from flask.sessions import SecureCookieSessionInterface

from support import (Results, create_admin, log_in, temp_database, temp_folder,
                     TEST_ADMIN)

import app

OLD_FALLBACK_KEY = "dev-key-not-a-secret"   # committed until Stage 20


def signed(payload, key):
    """A session cookie holding payload, signed with key -- a forgery, when the
    key is not the app's own."""
    signer = SimpleNamespace(secret_key=key, config=app.app.config)
    return SecureCookieSessionInterface().get_signing_serializer(signer).dumps(payload)


def admin_page(client):
    """200 if this client is treated as a logged-in admin, 302 if not."""
    return client.get("/admin").status_code


def raises(call):
    try:
        call()
    except RuntimeError as error:
        return str(error)
    return None


def secret_key(results):
    print("  The signing key is nobody else's")
    try:
        with temp_folder() as folder:
            app.configure({}, instance_path=folder)
            # Read only if it is there: a missing file is a FAIL to report,
            # not a FileNotFoundError that stops every check after it.
            key_file = folder / "secret_key"
            stored = key_file.read_text(encoding="ascii") if key_file.exists() else None
            results.check("development with no key generates one, on disk",
                          stored, app.app.secret_key)
            results.check("...of 64 hex characters", len(stored or ""), 64)
            app.configure({}, instance_path=folder)
            results.check("...and uses the same one next time", app.app.secret_key, stored)

            (folder / "secret_key").write_text("short", encoding="ascii")
            results.check("a damaged key file is refused, not used",
                          raises(lambda: app.configure({}, instance_path=folder)) is not None,
                          True)

        with temp_folder() as folder:
            given = "k" * app.MIN_SECRET_KEY_LENGTH
            app.configure({"ART_GALLERY_SECRET_KEY": given}, instance_path=folder)
            results.check("the environment's key wins", app.app.secret_key, given)
            results.check("...and no file is written", (folder / "secret_key").exists(), False)

            message = raises(lambda: app.configure(
                {"ART_GALLERY_SECRET_KEY": "k" * (app.MIN_SECRET_KEY_LENGTH - 1)},
                instance_path=folder))
            results.check("a key one character too short is refused", message is not None, True)

            message = raises(lambda: app.configure(
                {"ART_GALLERY_ENV": "production"}, instance_path=folder))
            results.check("production without a key refuses to start", message is not None, True)
            results.check("...and does not quietly make a key file",
                          (folder / "secret_key").exists(), False)

            message = raises(lambda: app.configure(
                {"ART_GALLERY_ENV": "prod", "ART_GALLERY_SECRET_KEY": given},
                instance_path=folder))
            results.check('a typo ("prod") is refused, not read as development',
                          message is not None, True)
    finally:
        app.configure(os.environ)       # back to this run's own test key

    print("  Forged cookies are refused")
    create_admin()
    with app.app.app_context():
        admin_id = app.get_admin_by_username(TEST_ADMIN)["id"]

    for payload, label in (({"admin_id": admin_id}, "the old shape"),
                           ({"admin": {"id": admin_id, "key": "x", "at": int(time.time())}},
                            "the new shape")):
        forger = app.app.test_client()
        forger.set_cookie("session", signed(payload, OLD_FALLBACK_KEY))
        results.check(f"signed with the old committed key ({label}): no admin",
                      admin_page(forger), 302)

    # Even someone holding THIS app's key cannot guess the session_key, which
    # lives only in the database.
    forger = app.app.test_client()
    forger.set_cookie("session", signed(
        {"admin": {"id": admin_id, "key": "0" * 32, "at": int(time.time())}},
        app.app.secret_key))
    results.check("signed with the real key but a guessed session_key: no admin",
                  admin_page(forger), 302)


def production(results):
    print("  Production cookies are Secure, and HTTPS is insisted on")
    visitor = app.app.test_client()
    response = visitor.post("/cart/add", data={"artwork_id": "2"})
    cookie = response.headers.get("Set-Cookie", "")
    results.check("development: cookie named session", cookie.startswith("session="), True)
    results.check("development: not Secure (plain http)", "Secure" in cookie, False)
    results.check("development: no HSTS",
                  response.headers.get("Strict-Transport-Security"), None)

    try:
        app.configure({"ART_GALLERY_ENV": "production",
                       "ART_GALLERY_SECRET_KEY": app.app.secret_key,
                       "ART_GALLERY_HOSTS": "gallery.example"})
        visitor = app.app.test_client()
        response = visitor.post("/cart/add", data={"artwork_id": "2"},
                                base_url="https://gallery.example")
        cookie = response.headers.get("Set-Cookie", "")
        results.check("production: cookie named __Host-session",
                      cookie.startswith("__Host-session="), True)
        for part in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            results.check(f"production: {part}", part in cookie, True)
        results.check("production: no Domain (the __Host- rules forbid one)",
                      "Domain=" in cookie, False)
        results.check("production: HSTS for a year",
                      response.headers.get("Strict-Transport-Security"),
                      f"max-age={app.ONE_YEAR}")
    finally:
        app.configure(os.environ)


def admin_sessions(results):
    print("  An admin login ends when it should, everywhere")
    create_admin()

    # The audit's attack: copy the cookie, log out, use the copy.
    victim = app.app.test_client()
    log_in(victim)
    copy = victim.get_cookie("session").value
    victim.post("/admin/logout")
    thief = app.app.test_client()
    thief.set_cookie("session", copy)
    results.check("a cookie copied before logout no longer works", admin_page(thief), 302)

    laptop, phone = app.app.test_client(), app.app.test_client()
    log_in(laptop)
    log_in(phone)
    results.check("two devices logged in", (admin_page(laptop), admin_page(phone)),
                  (200, 200))
    laptop.post("/admin/logout")
    results.check("logging out on one logs out the other", admin_page(phone), 302)

    log_in(laptop)
    results.check("logging in again after that works", admin_page(laptop), 200)
    with app.app.app_context():
        app.set_admin_password(TEST_ADMIN, "a completely new passphrase")
        app.get_db().close()
    results.check("a new password ends existing sessions", admin_page(laptop), 302)
    create_admin()      # the test password again, for the checks below

    print("  ...and after 12 hours at most")
    limit = app.ADMIN_SESSION_SECONDS
    for seconds_ago, expected, label in ((limit - 60, 200, "a minute short of the limit"),
                                         (limit, 302, "exactly at the limit"),
                                         (-3600, 302, "logged in 'in the future'")):
        client = app.app.test_client()
        log_in(client)
        with client.session_transaction() as session:
            login = dict(session["admin"])
            login["at"] = int(time.time()) - seconds_ago
            session["admin"] = login
        results.check(f"login {label}", admin_page(client), expected)

    with client.session_transaction() as session:
        results.check("a dead login is removed from the cookie", "admin" in session, False)

    print("  ...and a malformed login is no login, never a crash")
    for value in (1, "admin", [1], {"id": True, "key": "x", "at": 1},
                  {"id": 1, "key": None, "at": 1}, {"id": 1, "key": "x", "at": 1.5}):
        client = app.app.test_client()
        with client.session_transaction() as session:
            session["admin"] = value
        results.check(f"admin = {value!r}", admin_page(client), 302)


def main():
    results = Results()
    for case in (secret_key, production, admin_sessions):
        with temp_database():
            case(results)
        print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
