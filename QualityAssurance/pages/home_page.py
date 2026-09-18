"""The authenticated home page - "Welcome back, <user>!" and the four stage cards.

The cards themselves are static HTML; only their CTAs are real widgets, keyed
`stage_cta_0`..`stage_cta_2`. Stage 4 (Content Editor) deliberately has no
button - it opens from inside a campaign project once a draft exists.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

import config

from .sidebar import Sidebar
from .streamlit_app import StreamlitPage

#: Index of each stage's CTA button, matching HOME_STAGES in Web/src/main.py.
STAGE_FIND_YOUR_VOICE = 0
STAGE_BUSINESS_SURVEY = 1
STAGE_CAMPAIGN_PROJECTS = 2


class HomePage(StreamlitPage):
    path = "/"
    title_text = "Your workflow"

    def __init__(self, page: Page, base_url: str | None = None):
        super().__init__(page, base_url)
        self.nav = Sidebar(page)

    # ---- header -----------------------------------------------------------

    def welcome(self) -> Locator:
        return self.main.text("Welcome back,")

    def logged_in_user(self) -> str:
        text = self.welcome().first.inner_text().strip()
        return text.removeprefix("Welcome back,").strip().rstrip("!")

    def logout(self) -> None:
        self.main.click("🚪 Logout")

    # ---- stage cards ------------------------------------------------------

    def stage_card(self, title: str) -> Locator:
        """One of the four `.stage-chrome` cards, by its heading."""
        return self.main.root.locator(".stage-chrome").filter(has_text=title)

    def stage_titles(self) -> list[str]:
        cards = self.main.root.locator(".stage-chrome h3")
        return [cards.nth(i).inner_text().strip() for i in range(cards.count())]

    def go_to_find_your_voice(self) -> None:
        self.main.click_key(f"stage_cta_{STAGE_FIND_YOUR_VOICE}")

    def go_to_business_survey(self) -> None:
        self.main.click_key(f"stage_cta_{STAGE_BUSINESS_SURVEY}")

    def go_to_campaign_projects(self) -> None:
        self.main.click_key(f"stage_cta_{STAGE_CAMPAIGN_PROJECTS}")

    def content_editor_locked_note(self) -> Locator:
        """The Stage 4 card's note, shown in place of a CTA."""
        return self.main.root.locator(".stage-locked-note")

    # ---- assertions -------------------------------------------------------

    def expect_loaded(self) -> None:
        expect(self.welcome().first).to_be_visible(timeout=config.DEFAULT_TIMEOUT)
