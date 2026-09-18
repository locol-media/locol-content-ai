"""Shared fixtures.

`logged_in` is the one most tests want: a browser page already signed in and
sitting on the home page. Note that Streamlit keeps authentication in session
state, so a fixture must not reload the page afterwards - navigate with the
sidebar instead.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

import config
from pages import HomePage, LoginPage


@pytest.fixture(scope="session")
def base_url() -> str:
    return config.WEB_URL


@pytest.fixture(autouse=True)
def _timeouts(page: Page) -> None:
    page.set_default_timeout(config.DEFAULT_TIMEOUT)
    page.set_default_navigation_timeout(config.DEFAULT_TIMEOUT)


@pytest.fixture
def login_page(page: Page, base_url: str) -> LoginPage:
    return LoginPage(page, base_url).open()


@pytest.fixture
def logged_in(login_page: LoginPage) -> HomePage:
    """Signed in as the configured account, on the home page."""
    login_page.login()
    home = HomePage(login_page.page, login_page.base_url)
    home.expect_loaded()
    return home
