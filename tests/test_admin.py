"""
Is the admin area actually locked, and are passwords handled properly?

Run it:

    python tests/test_admin.py

Security code has a nasty property: it looks exactly the same whether it works
or not. A login page that lets everyone in still shows a login page. So every
promise here is checked from the outside, the way an attacker would check it.

Every admin in this file lives in a temporary database, deleted afterwards.
"""

import re
import sys

from support import (TEST_ADMIN, TEST_PASSWORD, Results, create_admin,
                     direct_connection, log_in, temp_database)

import app

# Routes under /admin that must work WITHOUT being logged in.
OPEN_ADMIN_ENDPOINTS = {"admin_login", "admin_login_submit", "admin_logout"}


def every_admin_route_is_locked(results):
    """Walk the whole routing table, rather than a hand-kept list of routes.

    A hand-kept list is only as good as the memory of whoever adds the next
    route. This finds every /admin route that exists -- including the ones
    Part 2 adds -- and proves each refuses a stranger. Forgetting
    @admin_required, or putting it ABOVE @app.get so Flask registers the
    unlocked view, fails here.
    """
    print("  Every /admin route refuses a visitor who is not logged in")
    client = app.app.test_client()
    checked = 0

    for rule in app.app.url_map.iter_rules():
        if not rule.rule.startswith("/admin") or rule.endpoint in OPEN_ADMIN_ENDPOINTS:
            continue

        # Fill any <int:id> style parameters with 1. The lock has to hold
        # before the route even looks at its parameters.
        path = re.sub(r"<[^>]+>", "1", rule.rule)

        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            response = client.open(path, method=method)
            location = response.headers.get("Location", "")
            results.check(f"{method} {rule.rule} sends a stranger to log in",
                          (response.status_code, "/admin/login" in location),
                          (302, True))
            checked += 1

    results.check("routes checked (at least the dashboard)", checked >= 1, True)

    # The public site must not advertise the admin area.
    home = client.get("/").get_data(as_text=True)
    results.check("the public homepage does not link to /admin",
                  'href="/admin' in home, False)


def passwords_are_hashed(results):
    print("  Passwords are stored as salted hashes")
    create_admin()
    create_admin("second", TEST_PASSWORD)     # the same password, on purpose

    with direct_connection() as connection:
        rows = connection.execute(
            "SELECT username, password_hash FROM admins ORDER BY id").fetchall()

    first, second = rows[0]["password_hash"], rows[1]["password_hash"]
    results.check("the password itself is not stored", TEST_PASSWORD in first, False)
    results.check("the hash names its method",
                  first.split(":")[0] in {"scrypt", "pbkdf2"}, True)
    # Same password, different salt, different hash. Without salt these two
    # rows would be identical, and cracking one would crack both.
    results.check("the same password hashes differently for two admins",
                  first != second, True)


def failed_logins(results):
    print("  Failed logins")
    create_admin()
    client = app.app.test_client()

    wrong = log_in(client, password="not the password at all")
    unknown = log_in(client, username="nobody-by-this-name")

    results.check("a wrong password is rejected with 400", wrong.status_code, 400)
    results.check("an unknown username is rejected with 400", unknown.status_code, 400)

    def message(response):
        found = re.search(r'role="alert">([^<]+)<', response.get_data(as_text=True))
        return found.group(1) if found else None

    # Identical wording, so the answer does not reveal which usernames exist.
    results.check("both failures say exactly the same thing",
                  message(wrong), message(unknown))

    results.check("the typed password is never sent back in the page",
                  "not the password at all" in wrong.get_data(as_text=True), False)

    results.check("still locked out afterwards",
                  client.get("/admin").status_code, 302)


def successful_login(results):
    print("  Logging in")
    create_admin()
    client = app.app.test_client()

    response = log_in(client)
    results.check("a correct login redirects", response.status_code, 302)
    results.check("...to the dashboard", response.headers["Location"], "/admin")

    page = client.get("/admin")
    results.check("the dashboard now opens", page.status_code, 200)
    results.check("it lists the collection", page.get_data(as_text=True).count("<tr>") >= 6, True)
    results.check("admin pages are never cached",
                  page.headers.get("Cache-Control"), "no-store")

    other = app.app.test_client()
    results.check("usernames are not case-sensitive",
                  log_in(other, username=TEST_ADMIN.upper()).status_code, 302)


def open_redirects_refused(results):
    """`next` is honoured only when it is a path on this site."""
    print("  The next= parameter cannot send anyone off-site")
    create_admin()

    cases = [
        ("/admin?view=all", "/admin?view=all"),       # ours: honoured
        ("https://evil.example/", "/admin"),          # another site
        ("//evil.example/", "/admin"),                # scheme-relative host
        ("/\\evil.example/", "/admin"),               # the backslash trick
        ("javascript:alert(1)", "/admin"),            # not a path at all
        ("", "/admin"),                               # nothing given
    ]
    for next_url, expected in cases:
        client = app.app.test_client()
        response = log_in(client, next_url=next_url)
        results.check(f"next={next_url!r} goes to", response.headers.get("Location"), expected)


def logging_out(results):
    print("  Logging out")
    create_admin()
    client = app.app.test_client()
    log_in(client)

    # A cart in the same browser, which logging out must not throw away.
    with client.session_transaction() as session:
        session["cart"] = {"2": 1}

    results.check("logout by GET is refused (405)",
                  client.get("/admin/logout").status_code, 405)
    results.check("...and did not log anyone out",
                  client.get("/admin").status_code, 200)

    client.post("/admin/logout")
    results.check("logout by POST works", client.get("/admin").status_code, 302)

    with client.session_transaction() as session:
        results.check("the visitor's cart survives logging out",
                      session.get("cart"), {"2": 1})


def deleted_admin_is_locked_out(results):
    """The cookie says who you WERE. The database says who you are."""
    print("  Removing an admin locks them out at once")
    create_admin()
    client = app.app.test_client()
    log_in(client)
    results.check("logged in", client.get("/admin").status_code, 200)

    with direct_connection() as connection:
        connection.execute("DELETE FROM admins")
        connection.commit()

    results.check("the very next request is refused",
                  client.get("/admin").status_code, 302)


def the_command(results):
    """flask create-admin, driven the way Click lets a test drive it."""
    print("  flask create-admin")
    runner = app.app.test_cli_runner()

    short = runner.invoke(args=["create-admin", "cli-user"], input="tooshort\ntooshort\n")
    results.check("a short password is refused", short.exit_code != 0, True)
    results.check("...saying why", "at least 12" in short.output, True)

    made = runner.invoke(args=["create-admin", "cli-user"],
                         input=f"{TEST_PASSWORD}\n{TEST_PASSWORD}\n")
    results.check("a good password creates the admin", made.exit_code, 0)
    results.check("the password is not echoed to the terminal",
                  TEST_PASSWORD in made.output, False)

    client = app.app.test_client()
    results.check("that admin can log in",
                  log_in(client, username="cli-user").status_code, 302)

    kept = runner.invoke(args=["create-admin", "cli-user"], input="n\n")
    results.check("declining to change an existing admin changes nothing",
                  "Nothing changed" in kept.output, True)


def main():
    results = Results()

    for case in (every_admin_route_is_locked, passwords_are_hashed,
                 failed_logins, successful_login, open_redirects_refused,
                 logging_out, deleted_admin_is_locked_out, the_command):
        with temp_database():
            case(results)
        print()

    return results.report()


if __name__ == "__main__":
    sys.exit(main())
