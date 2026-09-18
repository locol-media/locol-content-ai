"""Stage 3 - Campaign Projects: create a project, its survey, and its post ideas.

One route (`/projectSurvey`) serves three different screens, chosen by session
state rather than by URL:

* **➕ Add New Project** while `show_create_project` is set (the sidebar's ➕),
* **the project survey**, a paged StreamlitSurvey like the business one,
* **the insights page**, reached by finishing the survey or by picking a
  project in the sidebar, which holds the post ideas and content generation.

`current_screen()` reports which one is showing.

Project survey questions are keyed `<question_key>_<project_id>`, so answering
one needs the project's id - `Sidebar.project_id(name)` reads it out of the
sidebar, and `use_project()` caches it here.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

import config

from .idea_card import IdeaCard
from .sidebar import Sidebar
from .streamlit_app import StreamlitPage

#: Question sets that ship with the app, as offered by the create-project dropdown.
QUESTION_SETS = ("Generated Story", "Default Question Set", "Tell your story")

#: Options of the Content Type dropdown on an idea (CONTENT_TYPE_OPTIONS in projectSurvey.py).
CONTENT_TYPES = (
    "Blog Post", "Social Media Post", "Video", "Email", "Newsletter",
    "White Paper", "Case Study", "Infographic", "Podcast", "Webinar",
)

#: The backend generates one draft per idea and rejects a longer batch.
MAX_IDEAS_PER_BATCH = 25

#: Label for "no writing style" in the 🎤 Voice pickers.
NO_VOICE = "— No voice —"


class CampaignProjectsPage(StreamlitPage):
    path = "/projectSurvey"

    def __init__(self, page: Page, base_url: str | None = None):
        super().__init__(page, base_url)
        self.nav = Sidebar(page)
        self._project_id: str | None = None

    # ---- which screen are we on ------------------------------------------

    def current_screen(self) -> str:
        """One of "create", "survey", "insights"."""
        if self.main.text("➕ Create New Project").count():
            return "create"
        if self.main.text("Strategic Discovery Progress:").count():
            return "survey"
        return "insights"

    def heading(self) -> str:
        """The h1, which is the project's name once one is selected."""
        return self.main.root.locator("h1.main-header").inner_text().strip()

    def no_project_warning(self) -> Locator:
        return self.main.warning("Please select a project first")

    # ---- project selection ------------------------------------------------

    def use_project(self, name: str) -> "CampaignProjectsPage":
        """Open a project from the sidebar and remember its id."""
        self._project_id = self.nav.project_id(name)
        self.nav.open_project(name)
        return self

    @property
    def project_id(self) -> str:
        if self._project_id is None:
            raise AssertionError(
                "No project selected - call use_project(name) first, so the survey's "
                "widget keys (<question_key>_<project_id>) can be built."
            )
        return self._project_id

    # ---- ➕ Add New Project ------------------------------------------------

    def open_create_project(self) -> None:
        self.nav.new_project()

    def create_project(self, name: str, question_set: str = "Generated Story") -> None:
        """Fill in and submit the create-project panel.

        The question set is fixed at creation and decides which questions the
        project survey asks, so it cannot be changed afterwards.
        """
        self.main.expand("➕ Create New Project")
        self.main.fill("new_project_name", name)
        self.main.select("new_project_question_set", question_set)
        self.main.click("Create Project")

    def cancel_create_project(self) -> None:
        self.main.click("Cancel")

    def available_question_sets(self) -> list[str]:
        self.main.widget("new_project_question_set").locator("input").click()
        options = self.page.locator(
            '[data-testid="stSelectboxVirtualDropdown"] [role="option"]'
        )
        names = [options.nth(i).inner_text().strip() for i in range(options.count())]
        self.page.keyboard.press("Escape")
        return names

    def created_message(self, name: str) -> Locator:
        return self.main.success(f"Created project: {name}")

    # ---- the project survey ----------------------------------------------

    def survey_progress(self) -> str:
        """"Strategic Discovery Progress: N of M"."""
        return self.main.root.locator(".progress-text").inner_text().strip()

    def survey_page_index(self) -> int:
        number = self.survey_progress().split(":")[1].split("of")[0].strip()
        return int(number) - 1

    def survey_page_count(self) -> int:
        return int(self.survey_progress().rsplit("of", 1)[1].strip())

    def answer(self, question_key: str, value: str) -> None:
        """Answer a project-survey question by its key from the question-set YAML.

        For example `q1`/`q2` on "Generated Story"; see Web/question-sets/.
        """
        self.main.fill(f"{question_key}_{self.project_id}", value)

    def answer_text(self, question_key: str) -> str:
        return self.main.value(f"{question_key}_{self.project_id}")

    def save_survey_page(self) -> None:
        self.main.click("💾 Save Page")

    def next_survey_page(self) -> None:
        self.main.click("Next ➡️")

    def previous_survey_page(self) -> None:
        self.main.click("⬅️ Previous")

    def complete_discovery(self) -> None:
        """Finish the survey and land on the insights page."""
        self.main.click("🎯 Complete Discovery & Generate Insights")

    def edit_project_survey(self) -> None:
        """From the insights page, back into the questions."""
        self.main.click("✏️ Edit Project Survey")

    # ---- insights page ----------------------------------------------------

    def insight_tab_labels(self) -> list[str]:
        tabs = self.main.root.locator('[data-testid="stTab"]')
        return [tabs.nth(i).inner_text().strip() for i in range(tabs.count())]

    def open_insight_tab(self, label: str) -> None:
        self.main.open_tab(label)

    def insight(self, question_text: str) -> Locator:
        """One question's panel, holding Your Response and Potential Campaign Angles."""
        return self.main.expander(f"💡 {question_text}")

    # ---- generating the post ideas ---------------------------------------

    def generate_campaigns(self) -> None:
        """🚀 Generate Strategic Campaigns - the AI call that produces the ideas.

        Like the story brainstorm, the click only sets a loading flag and
        reruns; the AI call happens on the run after that. Waiting for the
        outcome rather than for idle avoids returning in the gap between them.
        """
        self.main.button("🚀 Generate Strategic Campaigns").click()
        self.page.wait_for_selector(
            '[data-testid="stAlertContentSuccess"]:has-text("brainstorming completed"), '
            '[data-testid="stAlertContentError"]',
            timeout=config.LLM_TIMEOUT,
        )
        self.wait_for_llm()

    def clear_strategic_response(self) -> None:
        """Delete every idea in this project. Unlike the story version, permanent."""
        self.main.click("🗑️ Clear Strategic Response")

    # ---- the ideas --------------------------------------------------------

    def idea_titles(self) -> list[str]:
        """Ideas in display order. The first is always the series introduction.

        Scoped to the *header* row of each card - the one carrying the ✏️ Edit
        button - because an idea's View Details panel is itself a columns block
        full of bold labels (Description, Content Type, Platform, Goal). Without
        that scope every idea contributes five matches instead of one.
        """
        titles = self.main.root.locator(
            '[data-testid="stHorizontalBlock"]:has([class*="st-key-edit_"]) '
            '[data-testid="stMarkdown"] strong'
        )
        return [titles.nth(i).inner_text().strip() for i in range(titles.count())]

    def idea(self, title: str) -> IdeaCard:
        return IdeaCard(self, title)

    def close_idea_editor(self) -> bool:
        """Cancel an open ✏️ Edit Idea panel, if there is one.

        Worth calling before anything that needs the idea list: while a panel is
        open the list is not rendered at all, so every card lookup fails - and
        the app blocks navigation until the edit is saved or cancelled.
        """
        cancel = self.main.button("❌ Cancel")
        if not cancel.count():
            return False
        cancel.click()
        self.wait_until_idle()
        return True

    def add_idea_manually(
        self,
        title: str,
        description: str = "",
        content_type: str = "Blog Post",
        platform: str = "Reddit",
        goal: str = "",
    ) -> None:
        """The ➕ Add Campaign Idea Manually form. Title is the only required field."""
        form = self.main.expand("➕ Add Campaign Idea Manually")
        form.get_by_label("Title", exact=True).fill(title)
        form.get_by_label("Description", exact=True).fill(description)
        # No key on this selectbox, so it is reached through the form.
        self.main.select_in(form.locator('[data-testid="stSelectbox"]'), content_type)
        form.get_by_label("Platform", exact=True).fill(platform)
        form.get_by_label("Goal", exact=True).fill(goal)
        form.locator('button:visible:has(p:text-is("➕ Add Idea"))').click()
        self.wait_until_idle()

    # ---- content generation ----------------------------------------------

    def selection_summary(self) -> Locator:
        """"✅ N idea(s) selected for content generation"."""
        return self.main.success("selected for content generation")

    def selected_count(self) -> int:
        if not self.selection_summary().count():
            return 0
        text = self.selection_summary().first.inner_text()
        return int(text.split("✅", 1)[1].split("idea", 1)[0].strip())

    def choose_voice(self, voice_name: str = NO_VOICE) -> None:
        """Pick the writing style drafts are generated in.

        Stored against the project, so this is the same selection as the picker
        inside an idea's brainstorm panel.
        """
        self.main.select(f"generate_voice_{self.project_id}", voice_name)

    def selected_voice(self) -> str:
        return self.main.selected_option(f"generate_voice_{self.project_id}")

    def voice_options(self) -> list[str]:
        """Every voice the picker offers, starting with `NO_VOICE`."""
        return self.main.options(f"generate_voice_{self.project_id}")

    def generate_content(self) -> None:
        """Draft every ticked idea. Disabled while nothing is selected.

        Runs one AI call per selected idea, so a batch takes roughly its size
        times a single draft.
        """
        self.main.button("🚀 Generate Content").click()
        self.page.wait_for_selector(
            '[data-testid="stAlertContentSuccess"]:has-text("Successfully generated content"), '
            '[data-testid="stAlertContentError"]',
            timeout=config.LLM_TIMEOUT,
        )
        self.wait_for_llm()

    def generate_content_button(self) -> Locator:
        return self.main.button("🚀 Generate Content")

    def refresh_content(self) -> None:
        """Re-read the drafts, e.g. after editing one in the Content Editor."""
        self.main.click("🔄 Refresh Content")

    def clear_selection(self) -> None:
        self.main.click("🗑️ Clear Selection")

    def batch_limit_warning(self) -> Locator:
        return self.main.warning("batches are limited to")

    # ---- assertions -------------------------------------------------------

    def expect_insights_screen(self) -> None:
        expect(self.main.text("🎯 Project Survey").first).to_be_visible(
            timeout=config.DEFAULT_TIMEOUT
        )

    def expect_idea_count(self, count: int) -> None:
        assert len(self.idea_titles()) == count, (
            f"expected {count} ideas, found {self.idea_titles()}"
        )
