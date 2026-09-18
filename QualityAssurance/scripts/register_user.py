"""Register a new user through the 📝 Register tab, then prove the account works.

Unnumbered on purpose: this creates the account the numbered scripts run
against, so it comes before all of them, but it consumes no state of its own and
is not one of the app's stages. Defaults to the throwaway QA account `test02` /
`blahTest02`.

Submitting the form is only half the job: the confirmation message says the
call succeeded, not that the account is usable, so this script signs in as the
new user before reporting success.

That check earned its keep immediately. A refusal the backend handles itself -
a username already taken - comes back as a 200 whose body carries
`success: false` (BackEnd/src/user_management.py), and Web's `register_user()`
used to treat any 200 as a win, so the form showed "✅ User registered
successfully!" over a registration that never happened. The verification login
is what surfaced it. Web now reads the `success` flag, so a rejection arrives
as an error here, but the login stays: it is the only thing that proves the
account works rather than that a request returned.

Two other behaviours shape the flow:

* **`/api/register-user` allows five attempts an hour** per client - BackEnd's
  `@limiter.limit("5/hour")` - so the script checks whether the account already
  works *before* spending one of them. Re-running against an account that
  exists costs no attempt and still exits 0.
* **A page load signs you out**, which is useful here: the landing page is
  reloaded between the probe login and the registration, so a stale "Invalid
  username or password" from the probe cannot be read back as a registration
  error. Streamlit switches tabs client-side without re-running the script, so
  that alert would otherwise still be sitting in the DOM.

Usage, from the QualityAssurance folder:

    .venv/Scripts/python scripts/register_user.py
    .venv/Scripts/python scripts/register_user.py --headed --slow-mo 300
    .venv/Scripts/python scripts/register_user.py --username test03 --password blahTest03
    .venv/Scripts/python scripts/register_user.py --email qa+test02@example.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run as a plain script, so make the suite's own modules importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The app's headings are full of emoji and a Windows console defaults to cp1252,
# which cannot encode them - printing a stage card would otherwise be the thing
# that fails, rather than anything to do with the account.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import Page, sync_playwright  # noqa: E402

import config  # noqa: E402
from pages import HomePage, LoginPage  # noqa: E402

# The account this script exists to create. Overridable on the command line;
# deliberately not config.USERNAME / config.PASSWORD, which name the *existing*
# account the rest of the suite signs in as.
USERNAME = "test02"
PASSWORD = "blahTest02"


def default_email(username: str) -> str:
    """The app requires an e-mail but puts no uniqueness constraint on it."""
    return f"{username}@example.com"


def attempt_login(page: Page, username: str, password: str) -> tuple[bool, str]:
    """Submit the login form; report whether it signed in, and what the app said.

    Expects the landing page to be on screen. Returns the welcomed username on
    success, and the app's own error text on failure, so the caller can print
    either without knowing which happened.
    """
    login = LoginPage(page)
    login.submit_login(username, password)

    home = HomePage(page)
    if home.welcome().count():
        return True, home.logged_in_user()

    errors = login.main.errors()
    return False, errors[0] if errors else "no error message shown"


def run(headed: bool, slow_mo: int, username: str, email: str, password: str) -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=slow_mo)
        page = browser.new_page()
        page.set_default_timeout(config.DEFAULT_TIMEOUT)

        try:
            print(f"Registering '{username}' on {config.WEB_URL}")

            # Cheap check first: a re-run should not spend one of the five
            # hourly registration attempts on an account that already works.
            LoginPage(page).open()
            print("\nChecking whether the account already exists...")
            existing, detail = attempt_login(page, username, password)
            if existing:
                print(f"  ✅ already registered - signed in as {detail}")
                print("     Nothing to do; these credentials work.")
                HomePage(page).logout()
                return 0
            print(f"  not signed in: {detail}")

            # Reload so the probe's error cannot be mistaken for a registration
            # failure. Free: we are not signed in to lose a session.
            login = LoginPage(page).open()

            print(f"\nSubmitting 📝 Register for '{username}' <{email}>")
            login.register(username, email, password)

            if login.main.error().count():
                print("  ❌ Registration was rejected:")
                for message in login.main.errors():
                    print(f"     {message}")
                return 1

            confirmation = login.main.success()
            if not confirmation.count():
                print("  ❌ No confirmation message appeared - the form did not submit.")
                return 1
            print(f"  {login.main.alert_text(confirmation)}")

            follow_up = login.main.info()
            if follow_up.count():
                print(f"  {login.main.alert_text(follow_up)}")
            print("  (says the call succeeded, not that the account works - hence the login below)")

            # The check that actually settles it. No reload needed: submitting
            # the login form re-runs the script, which clears the register
            # form's messages, so nothing above can be read back as a result.
            print("\nVerifying by signing in as the new account...")
            signed_in, detail = attempt_login(page, username, password)
            if not signed_in:
                print(f"  ❌ Could not sign in as '{username}': {detail}")
                print("     The registration did not take, despite the confirmation above.")
                return 1

            home = HomePage(page)
            print(f"  ✅ signed in as {detail}")
            # Proof the per-user database was seeded too: the four stage cards
            # only render for an initialised account.
            print(f"  home page offers: {', '.join(home.stage_titles())}")
            home.logout()

            print(f"\n✅ '{username}' is registered and can sign in.")
            print(f"   Point the suite at it with QA_USERNAME={username} and QA_PASSWORD=<password>")
            return 0

        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="show the browser")
    parser.add_argument(
        "--slow-mo", type=int, default=0, metavar="MS",
        help="pause between actions, to watch what it is doing",
    )
    parser.add_argument(
        "--username", default=USERNAME,
        help=f"account to create (default: {USERNAME})",
    )
    parser.add_argument(
        "--password", default=PASSWORD,
        help=f"its password (default: {PASSWORD})",
    )
    parser.add_argument(
        "--email", default=None, metavar="ADDRESS",
        help="e-mail for the account (default: <username>@example.com)",
    )
    args = parser.parse_args()
    return run(
        args.headed, args.slow_mo, args.username,
        args.email or default_email(args.username), args.password,
    )


if __name__ == "__main__":
    raise SystemExit(main())
