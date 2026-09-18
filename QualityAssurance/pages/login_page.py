"""The landing page: hero, 🔐 Login and 📝 Register.

Both tab panels are rendered into the DOM at once and the inactive one is
hidden, so every locator here is scoped to its own form rather than to the page.
The forms are anonymous in the DOM, but their submit buttons are keyed
`FormSubmitter-<form_key>-<label>`, which is what identifies each one.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

import config

from .streamlit_app import StreamlitPage, StreamlitRegion

LOGIN_FORM = ".st-key-FormSubmitter-login_form-Login"
REGISTER_FORM = ".st-key-FormSubmitter-registration_form-Register"


class LoginPage(StreamlitPage):
    path = "/"
    title_text = "Your story, told in your"

    def __init__(self, page: Page, base_url: str | None = None):
        super().__init__(page, base_url)
        # Each form is the vertical block that contains its own submit button.
        self._login = StreamlitRegion(
            page, page.locator(f'[data-testid="stForm"]:has({LOGIN_FORM})')
        )
        self._register = StreamlitRegion(
            page, page.locator(f'[data-testid="stForm"]:has({REGISTER_FORM})')
        )

    # ---- hero -------------------------------------------------------------

    @property
    def headline(self) -> Locator:
        return self.main.text("Your story, told in your")

    # ---- tabs -------------------------------------------------------------

    def open_login_tab(self) -> None:
        self.main.open_tab("🔐 Login")

    def open_register_tab(self) -> None:
        self.main.open_tab("📝 Register")

    # ---- login ------------------------------------------------------------

    @property
    def username(self) -> Locator:
        return self._login.input_by_label("Username")

    @property
    def password(self) -> Locator:
        return self._login.input_by_label("Password")

    @property
    def login_button(self) -> Locator:
        return self.main.button_by_key("FormSubmitter-login_form-Login")

    def login(self, username: str | None = None, password: str | None = None) -> None:
        """Sign in and wait for the authenticated home page."""
        self.open_login_tab()
        self.username.fill(username if username is not None else config.USERNAME)
        self.password.fill(password if password is not None else config.PASSWORD)
        self.login_button.click()
        self.wait_until_idle()

    def submit_login(self, username: str = "", password: str = "") -> None:
        """Submit the login form without expecting it to succeed."""
        self.open_login_tab()
        self.username.fill(username)
        self.password.fill(password)
        self.login_button.click()
        self.wait_until_idle()

    # ---- register ---------------------------------------------------------

    def register(self, username: str, email: str, password: str, confirm: str | None = None) -> None:
        self.open_register_tab()
        self._register.input_by_label("Username").fill(username)
        self._register.input_by_label("Email").fill(email)
        self._register.input_by_label("Password").fill(password)
        self._register.input_by_label("Confirm Password").fill(
            password if confirm is None else confirm
        )
        self.main.button_by_key("FormSubmitter-registration_form-Register").click()
        self.wait_until_idle()

    # ---- assertions -------------------------------------------------------

    def expect_logged_in(self, username: str | None = None) -> None:
        expect(
            self.main.text(f"Welcome back, {username or config.USERNAME}!")
        ).to_be_visible(timeout=config.DEFAULT_TIMEOUT)

    def error(self, text: str | None = None) -> Locator:
        return self.main.error(text)
