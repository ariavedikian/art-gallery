"""
Is the admin protected against guessing, and is production locked down?

Run it:

    python tests/test_protection.py

  throttle    failed logins are counted per IP address and per username;
              past the limit the form answers 429 without checking the
              password -- even a correct one
  hosts       only the site's own names are answered (TRUSTED_HOSTS)
  proxies     X-Forwarded-For is believed only when a proxy is declared
  checkout    production takes no mock payments, at the route AND in
              place_order()
  debug       `python app.py` refuses to start in production
"""

import os
import subprocess
import sys
import time

from support import (PROJECT_ROOT, TEST_PASSWORD, Results, buyer, create_admin,
                     direct_connection, temp_database)

import app

WRONG = "not the password at all"


def attempt(client, ip, username="curator", password=WRONG, forwarded=None):
    """One login attempt from `ip`. Returns the response."""
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return client.post("/admin/login", data={"username": username, "password": password},
                       environ_base={"REMOTE_ADDR": ip}, headers=headers)


def failures(where="1 = 1", params=()):
    with direct_connection() as db:
        return db.execute(f"SELECT COUNT(*) FROM login_failures WHERE {where}",
                          params).fetchone()[0]


def add_failures(rows):
    """Write failures directly: (ip, username, seconds ago) each."""
    now = int(time.time())
    with direct_connection() as db:
        db.executemany("INSERT INTO login_failures (ip, username, failed_at) "
                       "VALUES (?, ?, ?)", [(ip, name, now - ago) for ip, name, ago in rows])
        db.commit()


def production(**extra):
    """Switch the app to production with the settings it requires."""
    app.configure({"ART_GALLERY_ENV": "production",
                   "ART_GALLERY_SECRET_KEY": app.app.secret_key,
                   "ART_GALLERY_HOSTS": "gallery.example", **extra})


def throttle_by_ip(results):
    print("  Per IP: 10 failures in the window, then 429")
    create_admin()
    client = app.app.test_client()
    limit = app.LOGIN_LIMIT_PER_IP

    codes = [attempt(client, "203.0.113.1").status_code for _ in range(limit)]
    results.check(f"{limit} wrong passwords: each an ordinary 400", set(codes), {400})
    results.check("...each one counted", failures(), limit)

    response = attempt(client, "203.0.113.1", password=TEST_PASSWORD)
    results.check("then even the RIGHT password is refused, 429",
                  response.status_code, 429)
    wait = int(response.headers.get("Retry-After", "0"))
    results.check("...saying how long to wait (Retry-After, 1-900 s)",
                  0 < wait <= app.LOGIN_WINDOW_SECONDS, True)
    results.check("...and in words", "Too many failed attempts" in response.get_data(as_text=True), True)
    results.check("...and nobody was logged in", client.get("/admin").status_code, 302)
    results.check("a refused attempt is not counted (no table growth)", failures(), limit)

    other = app.app.test_client()
    results.check("another IP can still log in",
                  attempt(other, "198.51.100.7", password=TEST_PASSWORD).status_code, 302)

    stranger = app.app.test_client()
    codes = [attempt(stranger, "203.0.113.2", username="nobody").status_code
             for _ in range(limit + 1)]
    results.check("an unknown username is throttled exactly the same way",
                  codes[-1], 429)


def throttle_by_username(results):
    print("  Per username: 50 in the window, from anywhere, then 429")
    create_admin()
    limit = app.LOGIN_LIMIT_PER_USERNAME
    # 49 failures from 49 different addresses: none of them near the IP limit.
    add_failures([(f"192.0.2.{n}", "curator", 60) for n in range(limit - 1)])

    client = app.app.test_client()
    results.check("the 50th failure is still an ordinary 400",
                  attempt(client, "198.51.100.50").status_code, 400)
    results.check("then a fresh IP with the right password: 429",
                  attempt(client, "198.51.100.51", password=TEST_PASSWORD).status_code, 429)
    results.check("usernames are counted ignoring case, like logins",
                  attempt(client, "198.51.100.52", username="CURATOR",
                          password=TEST_PASSWORD).status_code, 429)
    results.check("another username from that IP is not affected",
                  attempt(client, "198.51.100.51", username="someone").status_code, 400)

    create_admin()          # flask create-admin: a new password
    results.check("a new password clears the username's failures",
                  attempt(client, "198.51.100.53", password=TEST_PASSWORD).status_code, 302)


def the_window(results):
    print("  Only the last 15 minutes count")
    create_admin()
    window = app.LOGIN_WINDOW_SECONDS
    add_failures([("203.0.113.9", "curator", window + 1)] * 10)
    client = app.app.test_client()
    results.check("10 failures just outside the window: login works",
                  attempt(client, "203.0.113.9", password=TEST_PASSWORD).status_code, 302)

    add_failures([("203.0.113.10", "curator", 600)] * 10)
    response = attempt(app.app.test_client(), "203.0.113.10", password=TEST_PASSWORD)
    wait = int(response.headers.get("Retry-After", "0"))
    results.check("10 failures 10 minutes ago: wait about 5 more minutes",
                  window - 600 - 2 <= wait <= window - 600, True)

    attempt(app.app.test_client(), "203.0.113.11")
    results.check("recording a failure deletes the ones outside the window",
                  failures("failed_at <= ?", (int(time.time()) - window,)), 0)


def hosts(results):
    print("  Only the site's own names are answered")
    client = app.app.test_client()
    for host, expected in (("localhost", 200), ("127.0.0.1:5000", 200),
                           ("evil.example", 400)):
        results.check(f"development, Host {host}",
                      client.get("/", headers={"Host": host}).status_code, expected)

    try:
        app.configure({"ART_GALLERY_HOSTS": "192.168.1.20, localhost"})
        results.check("ART_GALLERY_HOSTS adds a name in development (a phone on the LAN)",
                      client.get("/", headers={"Host": "192.168.1.20:5000"}).status_code, 200)

        message = None
        try:
            app.configure({"ART_GALLERY_ENV": "production",
                           "ART_GALLERY_SECRET_KEY": app.app.secret_key})
        except RuntimeError as error:
            message = str(error)
        results.check("production without ART_GALLERY_HOSTS refuses to start",
                      message is not None and "ART_GALLERY_HOSTS" in message, True)

        production()
        response = client.get("/api/artworks/1", base_url="https://gallery.example")
        results.check("production: its own name is answered", response.status_code, 200)
        results.check("...and the API's links use it",
                      response.get_json()["url"], "https://gallery.example/artwork/1")
        results.check("production: localhost is not",
                      client.get("/", base_url="https://localhost").status_code, 400)
    finally:
        app.configure(os.environ)


def proxies(results):
    print("  X-Forwarded-For is believed only behind a declared proxy")
    create_admin()
    limit = app.LOGIN_LIMIT_PER_IP
    client = app.app.test_client()

    # No proxy declared: a client writing the header cannot dodge the throttle.
    for n in range(limit):
        attempt(client, "203.0.113.20", forwarded=f"10.0.0.{n}")
    results.check("no proxy: a forged X-Forwarded-For is ignored (still 429)",
                  attempt(client, "203.0.113.20", forwarded="10.0.0.99").status_code, 429)

    try:
        app.configure({"ART_GALLERY_PROXIES": "1"})
        app.configure({"ART_GALLERY_PROXIES": "1"})
        results.check("configuring twice wraps the app once, not twice",
                      app.app.wsgi_app.app is app._plain_wsgi_app, True)

        # Behind one proxy, every request comes FROM the proxy (10.0.0.1).
        for _ in range(limit):
            attempt(client, "10.0.0.1", forwarded="198.51.100.30")
        results.check("one proxy: failures are counted for the visitor's address",
                      failures("ip = ?", ("198.51.100.30",)), limit)
        results.check("...so that visitor is throttled",
                      attempt(client, "10.0.0.1", forwarded="198.51.100.30").status_code, 429)
        results.check("...and another visitor through the same proxy is not",
                      attempt(client, "10.0.0.1", forwarded="198.51.100.31",
                              password=TEST_PASSWORD).status_code, 302)

        message = None
        try:
            app.configure({"ART_GALLERY_PROXIES": "two"})
        except RuntimeError as error:
            message = str(error)
        results.check("ART_GALLERY_PROXIES must be a whole number", message is not None, True)
    finally:
        app.configure(os.environ)
    results.check("back in development: no proxy", app.app.wsgi_app is app._plain_wsgi_app, True)


def checkout_closed(results):
    print("  Production takes no mock payments")
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["cart"] = {"2": 1}
    results.check("development: the mock checkout opens (baseline)",
                  client.get("/checkout").status_code, 200)

    with direct_connection() as db:
        stock = db.execute("SELECT inventory_quantity FROM artworks WHERE id = 2").fetchone()[0]
    try:
        production()
        https = {"base_url": "https://gallery.example"}
        shopper = app.app.test_client()
        with shopper.session_transaction(**https) as session:
            session["cart"] = {"2": 1}
        response = shopper.get("/checkout", **https)
        results.check("production: checkout is 503", response.status_code, 503)
        results.check("...saying purchases open soon",
                      "Purchases open soon" in response.get_data(as_text=True), True)
        results.check("posting the form anyway is 503 too",
                      shopper.post("/checkout", data=buyer(), **https).status_code, 503)
        results.check("the cart still works",
                      shopper.get("/cart", **https).status_code, 200)

        raised = False
        with app.app.test_request_context(**https):
            try:
                app.place_order([], buyer(), payment_approved=True)
            except RuntimeError:
                raised = True
        results.check("place_order() itself refuses (the second lock)", raised, True)
    finally:
        app.configure(os.environ)

    with direct_connection() as db:
        results.check("no order was written",
                      db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)
        results.check("no stock was taken", db.execute(
            "SELECT inventory_quantity FROM artworks WHERE id = 2").fetchone()[0], stock)


def debug_server(results):
    print("  `python app.py` will not start in production")
    env = dict(os.environ, ART_GALLERY_ENV="production",
               ART_GALLERY_SECRET_KEY=app.app.secret_key,
               ART_GALLERY_HOSTS="gallery.example")
    try:
        run = subprocess.run([sys.executable, "app.py"], cwd=PROJECT_ROOT, env=env,
                             capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        results.fail("it started a server (still running after 30 s)")
        return
    results.check("it exits with an error", run.returncode != 0, True)
    results.check("...saying why", "development server" in run.stderr + run.stdout, True)


def main():
    results = Results()
    for case in (throttle_by_ip, throttle_by_username, the_window, hosts,
                 proxies, checkout_closed):
        with temp_database():
            case(results)
        print()
    debug_server(results)
    print()
    return results.report()


if __name__ == "__main__":
    sys.exit(main())
