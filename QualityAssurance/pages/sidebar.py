"""The global sidebar - the app's real navigation.

Streamlit's own nav links are hidden by CSS in Web/src/main.py; every entry here
is a keyed `st.button`, which is what makes them addressable by key. Because a
page load would sign the session out, this component is the only supported way
to move between pages once logged in.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from .streamlit_app import StreamlitRegion


class Sidebar:
    """Navigation and project/idea tree shared by every authenticated page."""

    def __init__(self, page: Page):
        self.page = page
        self.region = StreamlitRegion(page, page.locator('[data-testid="stSidebar"]'))

    # ---- top-level destinations ------------------------------------------

    def go_home(self) -> None:
        self.region.click_key("nav_home")

    def go_to_config_manager(self) -> None:
        self.region.click_key("nav_config_manager")

    def go_to_find_your_voice(self) -> None:
        self.region.click_key("nav_find_your_voice")

    # ---- business survey section -----------------------------------------

    def business_survey_expanded(self) -> bool:
        """The toggle reads ▼ when open and ▶ when closed."""
        return self.region.button_by_key("nav_toggle_business_survey").inner_text().strip() == "▼"

    def toggle_business_survey(self) -> None:
        self.region.click_key("nav_toggle_business_survey")

    def expand_business_survey(self) -> None:
        if not self.business_survey_expanded():
            self.toggle_business_survey()

    def go_to_business_survey_page(self, index: int) -> None:
        """Jump straight to one of the four survey pages (0-based).

        0 🏢 Basic Business Information, 1 🎯 Goals & Strategy,
        2 💡 Skills & Expertise, 3 🎨 Hobbies & Interests.
        """
        self.expand_business_survey()
        self.region.click_key(f"nav_business_page_{index}")

    def go_to_business_survey(self) -> None:
        self.go_to_business_survey_page(0)

    # ---- campaign projects section ---------------------------------------

    def new_project(self) -> None:
        """The ➕ beside 📁 Campaign Projects - opens the create-project panel."""
        self.region.click_key("nav_add_project")

    def refresh_projects(self) -> None:
        self.region.click_key("nav_refresh_projects")

    def project_names(self) -> list[str]:
        buttons = self.region.root.locator('[class*="st-key-nav_project_"] button:visible')
        return [buttons.nth(i).inner_text().strip() for i in range(buttons.count())]

    def project(self, name: str) -> Locator:
        return self.region.root.locator(
            f'[class*="st-key-nav_project_"] button:visible:has(p:text-is("{name}"))'
        )

    def open_project(self, name: str) -> None:
        """Select a project and open its Campaign Projects page.

        Takes the first match: the app puts no uniqueness constraint on project
        names, and creating one from a story names it after the story, so two
        runs of the same script really can leave two identically named projects.
        """
        self.project(name).first.click()
        self.region.wait_until_idle()

    def project_id(self, name: str) -> str:
        """The project's id, read out of its button's `st-key-nav_project_<id>` class.

        Ids are needed to address a project survey's question widgets, whose keys
        are `<question_key>_<project_id>`.
        """
        container = self.region.root.locator(
            f'[class*="st-key-nav_project_"]:has(button:visible:has(p:text-is("{name}")))'
        ).first
        classes = container.get_attribute("class") or ""
        for token in classes.split():
            if token.startswith("st-key-nav_project_"):
                return token[len("st-key-nav_project_"):]
        raise AssertionError(f"No project named {name!r} in the sidebar")

    def toggle_project(self, name: str) -> None:
        """Expand or collapse a project's 💡 idea list."""
        project_id = self.project_id(name)
        self.region.click_key(f"nav_toggle_{project_id}")

    def idea_titles(self, project_name: str) -> list[str]:
        """Idea entries under an expanded project, without their 💡 prefix."""
        self.toggle_project(project_name)
        buttons = self.region.root.locator('[class*="st-key-nav_idea_"] button:visible')
        titles = [buttons.nth(i).inner_text().strip() for i in range(buttons.count())]
        return [t.lstrip("　").removeprefix("💡 ").strip() for t in titles]

    def open_idea(self, title: str) -> None:
        """Jump to a specific idea inside its project.

        The project must already be expanded (see `toggle_project`). Blocked by
        the app if an idea edit is still open, which surfaces as a warning:
        "⚠️ Please save or cancel your idea edits before navigating."
        """
        self.region.root.locator(
            f'[class*="st-key-nav_idea_"] button:visible:has-text("{title}")'
        ).first.click()
        self.region.wait_until_idle()

    def edit_in_progress_warning(self) -> Locator:
        return self.region.warning("save or cancel your idea edits")
