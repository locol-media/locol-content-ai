"""Stage 2 - 🚀 Business Content Discovery Tool, and the story brainstorm on page 4.

Every question is addressed by the field key from
`Web/question-sets/business_survey_questions.yaml`, because StreamlitSurvey
passes that key straight to the widget and it therefore becomes the widget's
`st-key-` class. The `FIELDS` map below is the same file's contents, kept here
so a test can say `page.fill(BusinessSurveyPage.BUSINESS_NAME, ...)` and fail
loudly if the YAML is renamed.

There is one business survey per account: saving replaces the previous answers
rather than adding a second one.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

import config

from .sidebar import Sidebar
from .streamlit_app import StreamlitPage

TOTAL_PAGES = 4

#: Page index -> heading, matching business_survey_page_configs.yaml.
PAGE_TITLES = {
    0: "🏢 Basic Business Information",
    1: "🎯 Goals & Strategy",
    2: "💡 Skills & Expertise",
    3: "🎨 Hobbies & Interests",
}

#: Page index -> the field keys that page renders, in order.
PAGE_FIELDS = {
    0: [
        "business_name",
        "business_description",
        "industry",
        "industry_other",  # only rendered when industry == "Other"
        "target_audience",
        "services",
        "unique_value",
    ],
    1: [
        "business_goals",
        "audience_interests",
        "current_content",
        "competitors",
        "influencers",
    ],
    2: [
        "professional_expertise",
        "years_experience",
        "technical_skills",
        "credentials",
        "problems_solved",
        "unique_approach",
        "industry_mistakes",
    ],
    3: [
        "personal_hobbies",
        "active_hobbies",
        "creative_hobbies",
        "learning_interests",
        "hobby_communities",
        "hobbies_and_business",
        "audience_overlap",
    ],
}

#: Page index -> the YAML category it comes from.
PAGE_CATEGORIES = {
    0: "basic_info",
    1: "goals_strategy",
    2: "challenges_market",
    3: "content_preferences",
}

#: The four questions the app refuses to advance past while blank.
REQUIRED_FIELDS = (
    "business_name",
    "business_description",
    "industry",
    "target_audience",
    "business_goals",
)


class BusinessSurveyPage(StreamlitPage):
    path = "/survey"
    title_text = "🚀 Business Content Discovery Tool"

    # Convenience aliases for the fields tests touch most.
    BUSINESS_NAME = "business_name"
    BUSINESS_DESCRIPTION = "business_description"
    INDUSTRY = "industry"
    INDUSTRY_OTHER = "industry_other"
    TARGET_AUDIENCE = "target_audience"
    BUSINESS_GOALS = "business_goals"

    def __init__(self, page: Page, base_url: str | None = None):
        super().__init__(page, base_url)
        self.nav = Sidebar(page)

    # ---- progress ---------------------------------------------------------

    def progress_text(self) -> str:
        """"Survey Progress: N of 4"."""
        return self.main.root.locator(".progress-text").inner_text().strip()

    def current_page_index(self) -> int:
        """0-based index of the page on screen."""
        number = self.progress_text().split(":")[1].split("of")[0].strip()
        return int(number) - 1

    def page_heading(self) -> str:
        return self.main.root.locator("h2.section-header").inner_text().strip()

    def legend(self) -> Locator:
        """The line saying whether this page has required questions."""
        return self.main.root.locator('[data-testid="stCaptionContainer"]').first

    # ---- answering --------------------------------------------------------

    def fill(self, field_key: str, value: str) -> None:
        """Answer a text question."""
        self.main.fill(field_key, value)

    def answer(self, field_key: str) -> str:
        return self.main.value(field_key)

    def choose_industry(self, industry: str) -> None:
        self.main.select(self.INDUSTRY, industry)

    def selected_industry(self) -> str:
        return self.main.selected_option(self.INDUSTRY)

    def add_goal(self, goal: str) -> None:
        self.main.multiselect_add(self.BUSINESS_GOALS, goal)

    def selected_goals(self) -> list[str]:
        return self.main.multiselect_values(self.BUSINESS_GOALS)

    def field(self, field_key: str) -> Locator:
        """The widget container, for existence/visibility assertions.

        `industry_other` is only in the DOM once "Other" is the chosen industry.
        """
        return self.main.widget(field_key)

    # ---- navigation -------------------------------------------------------

    def save_page(self) -> None:
        self.main.click("💾 Save Page")

    def next_page(self) -> None:
        """Advance. Blocked, with an error listing them, if required fields are blank."""
        self.main.click("Next ➡️")

    def previous_page(self) -> None:
        self.main.click("⬅️ Previous")

    def save_survey(self) -> None:
        """The last page's 💾 Save Business Survey, which replaces Next ➡️."""
        self.main.click("💾 Save Business Survey")

    def go_to_page(self, index: int) -> None:
        self.nav.go_to_business_survey_page(index)

    def missing_required_error(self) -> Locator:
        return self.main.error("Please answer these required questions")

    # ---- Stage 2b: story ideas (fourth page only) -------------------------

    def generate_story_ideas(self) -> None:
        """Run the story brainstorm. Replaces any previously generated set.

        The click does not itself run the AI: it sets a loading flag and reruns,
        and the call happens on the *next* run. Waiting only for the app to go
        idle would therefore return in the gap between the two, so this waits
        for the outcome - the success message or an error - instead.
        """
        self.main.button("✨ Generate Story Ideas").click()
        self.page.wait_for_selector(
            '[data-testid="stAlertContentSuccess"]:has-text("Story ideas generated"), '
            '[data-testid="stAlertContentError"]',
            timeout=config.LLM_TIMEOUT,
        )
        self.wait_for_llm()

    def clear_story_ideas(self) -> None:
        """Hide the list. Unlike the project version this does not delete anything."""
        self.main.click("🗑️ Clear Story Ideas")

    def story_idea(self, title: str) -> Locator:
        return self.main.expander(f"📖 {title}")

    def story_idea_titles(self) -> list[str]:
        summaries = self.main.root.locator('[data-testid="stExpander"] summary')
        titles = [summaries.nth(i).inner_text().strip() for i in range(summaries.count())]
        return [t.split("📖", 1)[-1].strip() for t in titles if "📖" in t]

    def open_story_idea(self, title: str) -> Locator:
        return self.main.expand(f"📖 {title}")

    def create_project_from_story(self, title: str) -> None:
        """The 🚀 Create Project button inside a story panel.

        Creates a campaign project named after the story, on the "Generated
        Story" question set, pre-filled with a business survey summary and the
        story's angle.
        """
        panel = self.open_story_idea(title)
        panel.locator('button:visible:has(p:text-is("🚀 Create Project"))').click()
        self.wait_until_idle()

    def project_created_message(self) -> Locator:
        return self.main.success("created! Open the Projects page to continue")

    # ---- assertions -------------------------------------------------------

    def expect_on_page(self, index: int) -> None:
        expect(self.main.text(f"Survey Progress: {index + 1} of {TOTAL_PAGES}")).to_be_visible(
            timeout=config.DEFAULT_TIMEOUT
        )
