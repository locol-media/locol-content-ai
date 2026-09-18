"""Read-only checks that the page objects still line up with the app.

Deliberately free of writes: nothing here creates, edits or deletes anything in
the account under test, and nothing calls an LLM. They exist to catch the
locators going stale after a UI change, which is what usually breaks a page
object first.
"""
import pytest

from pages import (
    BusinessSurveyPage,
    ConfigManagerPage,
    FindYourVoicePage,
    HomePage,
)
from pages.business_survey_page import PAGE_TITLES

pytestmark = pytest.mark.smoke


def test_landing_page_offers_login_and_register(login_page):
    assert login_page.headline.first.is_visible()
    login_page.open_register_tab()
    login_page.open_login_tab()
    assert login_page.login_button.is_enabled()


def test_login_rejects_empty_credentials(login_page):
    login_page.submit_login()
    assert login_page.error("Please enter both username and password").count() == 1


def test_home_shows_the_four_stages(logged_in: HomePage):
    assert logged_in.stage_titles() == [
        "Find Your Voice",
        "Business Survey",
        "Campaign Projects",
        "Content Editor",
    ]
    assert logged_in.content_editor_locked_note().count() == 1


def test_business_survey_pages_are_reachable_from_the_sidebar(logged_in: HomePage):
    survey = BusinessSurveyPage(logged_in.page, logged_in.base_url)
    logged_in.go_to_business_survey()
    survey.wait_until_loaded()

    for index, title in PAGE_TITLES.items():
        survey.go_to_page(index)
        survey.expect_on_page(index)
        assert survey.page_heading() == title


def test_required_business_survey_fields_are_present(logged_in: HomePage):
    survey = BusinessSurveyPage(logged_in.page, logged_in.base_url)
    logged_in.go_to_business_survey()
    survey.wait_until_loaded()

    for key in ("business_name", "business_description", "industry", "target_audience"):
        assert survey.field(key).count() == 1, f"{key} is missing from page 1"
    # The follow-up only exists once "Other" is the chosen industry.
    assert survey.field("industry_other").count() == 0


def test_config_manager_lists_its_three_tabs(logged_in: HomePage):
    config_page = ConfigManagerPage(logged_in.page, logged_in.base_url)
    logged_in.nav.go_to_config_manager()
    config_page.wait_until_loaded()

    config_page.open_llms()
    assert config_page.llm(config_page.llm_names()[0]).count() == 1
    config_page.open_channels()
    config_page.open_prompts()


def test_find_your_voice_reports_whether_reddit_analysis_is_offered(logged_in: HomePage):
    voices = FindYourVoicePage(logged_in.page, logged_in.base_url)
    logged_in.nav.go_to_find_your_voice()
    voices.wait_until_loaded()

    if voices.analyse_enabled():
        assert voices.unavailable_warning().count() == 0
    else:
        assert voices.unavailable_warning().count() == 1
