"""Page objects for the Locol Content AI UI.

Two applications are covered:

* the **Streamlit app** (Web/) - login, the business survey, campaign projects,
  Find Your Voice and the Config Manager. Everything here derives from
  `StreamlitPage`, and the sidebar is the only supported way to move between
  its pages, because a page load ends the session.
* the **Content Editor** (FrontEnd/, served by BackEnd under /www) - a plain
  static page, so `ContentEditorPage` stands on its own.

Typical use:

    LoginPage(page).open().login()
    HomePage(page).expect_loaded()

    projects = CampaignProjectsPage(page)
    projects.use_project("My story").idea("First post").select_for_generation()
"""
from .business_survey_page import BusinessSurveyPage
from .campaign_projects_page import CampaignProjectsPage
from .config_manager_page import ConfigManagerPage
from .content_editor_page import ContentEditorPage
from .find_your_voice_page import FindYourVoicePage
from .home_page import HomePage
from .idea_card import IdeaCard, IdeaEditPanel
from .login_page import LoginPage
from .sidebar import Sidebar
from .streamlit_app import StreamlitPage, StreamlitRegion

__all__ = [
    "BusinessSurveyPage",
    "CampaignProjectsPage",
    "ConfigManagerPage",
    "ContentEditorPage",
    "FindYourVoicePage",
    "HomePage",
    "IdeaCard",
    "IdeaEditPanel",
    "LoginPage",
    "Sidebar",
    "StreamlitPage",
    "StreamlitRegion",
]
