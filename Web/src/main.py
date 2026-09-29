import streamlit as st
import sys
import os
import requests
import json
from datetime import datetime

# Add the current directory and locol-lib to Python path so we can import survey modules
current_dir = os.path.dirname(os.path.abspath(__file__))
locol_lib_dir = os.path.join(current_dir, "locol-lib")
for path in (current_dir, locol_lib_dir):
    if path not in sys.path:
        sys.path.append(path)

# Logo path
LOGO_PATH = os.path.join(current_dir, "locol-logo.png")

from apiClient import LOCOL_API_URL, LOCOL_WWW_URL, get_api_headers
# Shared library modules only - never import a page module (projectSurvey.py,
# survey.py, ...) from here: that re-runs the page's top-level Streamlit code on
# every page and makes any error in it break the whole app's sidebar.
from projectState import select_project
from surveyPages import get_business_survey_pages

# Set page config at the module level (before any other streamlit commands)
st.set_page_config(
    page_title="Locol Content AI",
    page_icon=LOGO_PATH,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Hide the entire native nav (Home / Business Survey / Campaign Projects / Settings links).
# The pages must stay registered in st.navigation() for the custom sidebar sections below
# (render_home_nav / render_business_survey_nav / render_campaign_projects_nav / etc.) to
# keep using st.switch_page(), so this only visually hides them - no navigation logic changes.
st.markdown("""
<style>
    [data-testid="stSidebarNavItems"] { display: none; }
    [data-testid="stSidebarNavSeparator"] { display: none; }
</style>
""", unsafe_allow_html=True)

# Initialize session state for authentication
def init_auth_session():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'jwt_token' not in st.session_state:
        st.session_state.jwt_token = None

def clear_user_context():
    """Clear all user-specific session state when a different user signs in"""
    # Business survey context
    keys_to_clear = [
        'survey_data', 'survey_completed', 'business_survey_current_page',
        'content_ideas', 'llm_response', 'llm_loading', 'business_survey_loaded',
        # Project survey context
        'dropdown_list', 'selected_project', 'strategic_survey_data',
        'strategic_survey_completed', 'current_strategic_page', 'strategic_insights',
        'brainstorming_data', 'strategic_llm_loading', 'questions_config',
        'show_create_project', 'available_question_sets'
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

def register_user(username, email, password):
    """Register a new user"""
    try:
        payload = {
            "username": username,
            "email": email,
            "password": password,
            "created_at": datetime.now().isoformat()
        }
        
        response = requests.post(f"{LOCOL_API_URL}/api/register-user", 
                                json=payload, 
                                timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            # A refusal the backend handled itself - a username already taken,
            # say - comes back as a 200 carrying success: false, so the status
            # code alone would report a rejected registration as a new account.
            # Same shape as login_user() below, which reads `authenticated`.
            if not result.get("success"):
                message = result.get("message") or "Registration failed"
                error = result.get("error")
                return {"success": False, "message": f"{message} ({error})" if error else message}
            return {
                "success": True,
                "message": result.get("message") or "User registered successfully!",
                "user_id": result.get("user_id")
            }
        else:
            return {"success": False, "message": f"Registration failed: {response.text}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"Could not connect to server at {LOCOL_API_URL}"}
    except Exception as e:
        return {"success": False, "message": f"Error registering user: {str(e)}"}

def login_user(username, password):
    """Login user"""
    try:
        from jwt_utils import create_jwt_token
        
        payload = {
            "username": username,
            "password": password
        }
        
        response = requests.post(f"{LOCOL_API_URL}/api/login-user", 
                                json=payload, 
                                timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("authenticated"):
                user_id = result.get("user_id")
                jwt_token = create_jwt_token(user_id)
                return {
                    "success": True, 
                    "message": "Login successful!", 
                    "user_id": user_id,
                    "jwt_token": jwt_token
                }
            else:
                return {"success": False, "message": "Invalid username or password"}
        else:
            return {"success": False, "message": f"Login failed: {response.text}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"Could not connect to server at {LOCOL_API_URL}"}
    except Exception as e:
        return {"success": False, "message": f"Error logging in: {str(e)}"}

def show_login_form():
    """Display login form"""
    st.subheader("🔐 Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Login", type="primary", use_container_width=True)
        
        if submit_login:
            if username and password:
                result = login_user(username, password)
                if result["success"]:
                    # Clear context if different user is signing in
                    previous_user_id = st.session_state.get('user_id')
                    new_user_id = result["user_id"]
                    if previous_user_id and previous_user_id != new_user_id:
                        clear_user_context()

                    st.session_state.authenticated = True
                    st.session_state.user_id = new_user_id
                    st.session_state.jwt_token = result["jwt_token"]
                    st.session_state.username = username
                    st.success(result["message"])
                    st.rerun()
                else:
                    st.error(result["message"])
            else:
                st.error("Please enter both username and password")

def show_registration_form():
    """Display registration form"""
    st.subheader("📝 Register")
    
    with st.form("registration_form"):
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submit_register = st.form_submit_button("Register", type="secondary", use_container_width=True)
        
        if submit_register:
            if username and email and password and confirm_password:
                if password == confirm_password:
                    result = register_user(username, email, password)
                    if result["success"]:
                        st.success(result["message"])
                        st.info("Please login with your new credentials")
                    else:
                        st.error(result["message"])
                else:
                    st.error("Passwords do not match")
            else:
                st.error("Please fill in all fields")

# Define page functions
def home_page():
    """Home page with overview"""
    init_auth_session()

    col_logo, col_title, col_badge = st.columns([0.5, 3, 2])
    with col_logo:
        st.image(LOGO_PATH, width=60)
    with col_title:
        st.title("Locol Content AI")
    with col_badge:
        st.markdown("""
        <style>
          .header-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #1a1712;
            border: 1px solid rgba(245, 237, 224, 0.08);
            padding: 6px 14px;
            margin-top: 42px;
            float: right;
          }
          .header-badge .dot {
            width: 6px;
            height: 6px;
            background: #ff4500;
            border-radius: 50%;
          }
          .header-badge span {
            font-family: 'DM Mono', monospace;
            font-size: 0.7rem;
            color: #8a8070;
            letter-spacing: 0.1em;
            text-transform: uppercase;
          }
        </style>
        <div class="header-badge">
          <span class="dot"></span>
          <span>AI-Powered Reddit Storytelling</span>
        </div>
        """, unsafe_allow_html=True)
        if st.session_state.authenticated:
            _, logout_col = st.columns([3, 1])
            with logout_col:
                if st.button("🚪 Logout", type="secondary", use_container_width=True):
                    clear_user_context()
                    st.session_state.authenticated = False
                    st.session_state.user_id = None
                    st.session_state.jwt_token = None
                    st.session_state.username = None
                    st.success("Logged out successfully!")
                    st.rerun()
    
    if not st.session_state.authenticated:
        hero_col, auth_col = st.columns([0.63, 0.37], gap="large")

        with hero_col:
            # Hero + benefits, wrapped in one self-contained dark panel so the
            # branded palette (cream/orange/muted) has guaranteed contrast
            # regardless of Streamlit's actual page background - same
            # technique render_stage_overview()'s .stage-chrome cards use.
            st.markdown("""
            <style>
              /* No Playfair here: the hero headline is DM Sans like everything else in
                 this panel. DM Sans is requested at 900 and in italic because the
                 headline uses both (the emphasised "voice." is an italic 900) - without
                 those faces the browser synthesises them, which looks smeared at 4rem. */
              @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,700;0,900;1,400;1,900&display=swap');

              :root {
                --bg: #0f0d0a;
                --surface: #1a1712;
                --orange: #ff4500;
                --cream: #fffdf8;  /* warm near-white - headlines and labels */
                /* Secondary text. The old #8a8070 sat at ~5:1 on --bg - technically AA,
                   but hard going at 0.7-0.9rem. This is ~8.6:1 and still reads as a step
                   below --text. */
                --muted: #b8ab98;
                --text: #e8ddd0;
                --border: rgba(245, 237, 224, 0.08);
              }

              .hero-panel {
                --hero-inset: 1.1rem;
                background: var(--bg);
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 40px 44px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                /* Baseline for anything inside that inherits its colour: without this
                   it inherits Streamlit's dark page text, which is invisible here. */
                color: var(--text);
              }

              /* Everything in the panel is inset except the headline, which stays flush
                 left as the anchor the rest hangs off. One shared length, not 2ch: ch
                 resolves against each element's OWN font, so the 0.7rem DM Mono eyebrow
                 came out indented about half as far as the 1.05rem subhead above it and
                 the left edge read as ragged. 1.1rem is two characters at the subhead's
                 size, applied identically to every child. Kept as margin-left (a
                 longhand) so the per-element margin-bottom rules below still apply. */
              .hero-panel > *:not(.hero-title) {
                margin-left: var(--hero-inset);
              }

              /* Two-part selectors deliberately: Streamlit colours headings inside a
                 markdown container with "<emotion-class> h1" (specificity 0,1,1), which
                 outranks a bare .hero-title (0,1,0) and left the title rendering in the
                 dark page colour. Same reason .stage-chrome h3 below is scoped. */
              .hero-panel .hero-title {
                font-family: 'DM Sans', sans-serif;
                font-size: clamp(2.08rem, 3.2vw, 3.36rem);  /* 20% down from 2.6/4/4.2 */
                font-weight: 900;
                line-height: 1.05;
                color: var(--cream);
                letter-spacing: -0.03em;
                margin-bottom: 24px;
              }
              .hero-panel .hero-title em {
                font-style: italic;
                color: var(--orange);
              }

              .hero-sub {
                font-family: 'DM Sans', sans-serif;
                font-size: 1.05rem;
                line-height: 1.7;
                /* Body copy, not a label: --text, with --muted left to the small
                   uppercase eyebrows and descriptions below. */
                color: var(--text);
                max-width: 480px;
                margin-bottom: 30px;
              }

              .hero-benefits-eyebrow {
                font-family: 'DM Mono', monospace;
                font-size: 0.7rem;
                color: var(--muted);
                letter-spacing: 0.1em;
                text-transform: uppercase;
                margin-bottom: 14px;
              }

              .hero-benefits {
                display: flex;
                flex-direction: column;
                gap: 16px;
              }
              .benefit-row {
                display: flex;
                align-items: flex-start;
                gap: 12px;
              }
              .benefit-icon {
                font-size: 1.15rem;
                line-height: 1.5;
                flex-shrink: 0;
                width: 1.4em;
              }
              .benefit-copy {
                display: flex;
                flex-direction: column;
              }
              .benefit-title {
                font-family: 'DM Sans', sans-serif;
                font-weight: 700;
                font-size: 0.95rem;
                color: var(--cream);
                margin-bottom: 2px;
              }
              .benefit-desc {
                font-family: 'DM Sans', sans-serif;
                font-weight: 400;
                font-size: 0.88rem;
                line-height: 1.5;
                color: var(--muted);
                max-width: 460px;
              }
            </style>

            <div class="hero-panel">
              <h1 class="hero-title">Your story, told in your <em>voice.</em></h1>
              <p class="hero-sub">Locol Content AI plans, writes, and refines your Reddit posts — capturing exactly how you talk, so your story lands the way it deserves to.</p>

              <div class="hero-benefits-eyebrow">Why it works</div>
              <div class="hero-benefits">
                <div class="benefit-row">
                  <span class="benefit-icon">🎙️</span>
                  <div class="benefit-copy">
                    <span class="benefit-title">Sounds like you — not a chatbot</span>
                    <span class="benefit-desc">Save multiple voice profiles describing how you write, and every draft carries the one you pick — not a generic AI tone.</span>
                  </div>
                </div>
                <div class="benefit-row">
                  <span class="benefit-icon">💡</span>
                  <div class="benefit-copy">
                    <span class="benefit-title">Your expertise, already a story</span>
                    <span class="benefit-desc">Tell us about your business and get back concrete Reddit post ideas — never a blank page.</span>
                  </div>
                </div>
                <div class="benefit-row">
                  <span class="benefit-icon">🎯</span>
                  <div class="benefit-copy">
                    <span class="benefit-title">A sharpened angle before you write</span>
                    <span class="benefit-desc">Audience insight, timing, and positioning get worked out first, so your post has a real reason to land.</span>
                  </div>
                </div>
                <div class="benefit-row">
                  <span class="benefit-icon">🛡️</span>
                  <div class="benefit-copy">
                    <span class="benefit-title">You're always the final review</span>
                    <span class="benefit-desc">Every stage includes a human checkpoint — nothing publishes to Reddit without your go-ahead.</span>
                  </div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        with auth_col:
            # Deliberately no custom HTML panel here: st.tabs/st.form can't be
            # wrapped by a single markdown-injected <div> spanning multiple
            # st.* calls (same DOM constraint as render_stage_overview()'s
            # button styling), and this column sits on Streamlit's real page
            # background, so no custom --muted/--cream colors are used here -
            # avoids the same contrast trap the hero panel exists to avoid.
            # st.caption uses Streamlit's own themed muted-text style instead.
            st.markdown(
                '<p style="font-family: \'DM Sans\', sans-serif; font-size: 1.15rem; '
                'font-weight: 700; margin-bottom: 0.75rem;">Ready when you are — log in '
                'or create a free account below.</p>',
                unsafe_allow_html=True,
            )

            tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

            with tab1:
                show_login_form()

            with tab2:
                show_registration_form()
            
    else:
        # User is authenticated, show main content
        st.header(f"Welcome back, {st.session_state.username}!")

        render_stage_overview()




# Static "how this tool works" cards for the authenticated home page.
# Deliberately static: no dynamic progress/completion data and no extra API
# calls on page load - just guidance + a way to jump to each stage.
HOME_STAGES = [
    {
        "index": "STAGE 1",
        "icon": "🎤",
        "title": "Find Your Voice",
        "pill": "Optional",
        "pill_accent": False,
        "description": "Describe how you write and save it as a reusable voice profile, then pick it on a project so drafts sound like you. (Reddit analysis is unavailable — Reddit blocks it.)",
        "cta": "🎤 Manage Voices",
        "target": "locol-lib/findYourVoice.py",
        "locked_note": None,
    },
    {
        "index": "STAGE 2",
        "icon": "📝",
        "title": "Business Survey",
        "pill": "Recommended start",
        "pill_accent": True,
        "description": "Tell Locol Content AI about your business and expertise. You'll get back AI-generated story ideas to build on.",
        "cta": "📝 Start Business Survey",
        "target": "locol-lib/survey.py",
        "locked_note": None,
    },
    {
        "index": "STAGE 3",
        "icon": "🎯",
        "title": "Campaign Projects",
        "pill": None,
        "pill_accent": False,
        "description": "Turn a story idea into a project, sharpen your angle, and brainstorm specific Reddit post ideas for review.",
        "cta": "🎯 Open Campaign Projects",
        "target": "locol-lib/projectSurvey.py",
        "locked_note": None,
    },
    {
        "index": "STAGE 4",
        "icon": "✍️",
        "title": "Content Editor",
        "pill": "Unlocks later",
        "pill_accent": False,
        "description": "Draft with a prompt library and multiple LLMs side-by-side, then review and publish your Reddit post.",
        "cta": None,
        "target": None,
        "locked_note": "🔒 Opens from inside a Campaign Project once you've generated content for an idea.",
    },
]


def render_stage_overview():
    """Static stage-by-stage guidance cards, shown on the authenticated home page.

    Reuses the dark hero's design language (see the unauthenticated branch of
    home_page() above), but redeclares the :root tokens and font @import
    here rather than relying on the hero's - that block and this one sit in
    mutually exclusive if/else branches, so only one of them ever renders per
    page load.
    """
    st.markdown("""
    <style>
      /* Matches the hero's import above, for the same reasons: no Playfair, and DM Sans
         at 900 plus italic because .stages-title uses an italic 900 for its emphasis. */
      @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,700;0,900;1,400;1,900&display=swap');

      :root {
        --bg: #0f0d0a;
        --surface: #1a1712;
        --orange: #ff4500;
        --cream: #fffdf8;  /* warm near-white - keep in step with the hero's :root above */
        --muted: #b8ab98;  /* as above: brightened for legibility at small sizes */
        --text: #e8ddd0;
        --border: rgba(245, 237, 224, 0.08);
      }

      .stages-eyebrow {
        font-family: 'DM Mono', monospace;
        font-size: 0.7rem;
        color: var(--muted);
        letter-spacing: 0.1em;
        text-transform: uppercase;
      }
      .stages-title {
        font-family: 'DM Sans', sans-serif;
        font-size: clamp(1.8rem, 3vw, 2.4rem);
        font-weight: 900;
        color: var(--cream);
        letter-spacing: -0.02em;
        margin: 6px 0 10px;
      }
      .stages-title em {
        font-style: italic;
        color: var(--orange);
      }
      .stages-sub {
        font-family: 'DM Sans', sans-serif;
        font-size: 1rem;
        line-height: 1.6;
        color: var(--text);  /* body copy, same call as .hero-sub */
        max-width: 640px;
        margin-bottom: 8px;
      }

      .stage-chrome {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 20px 18px;
        min-height: 200px;
        display: flex;
        flex-direction: column;
        margin-bottom: 10px;
      }
      .stage-chrome-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
      }
      .stage-chrome-icon { font-size: 1.6rem; }
      .stage-chrome-index {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.7rem;
        color: var(--orange);
        letter-spacing: 0.1em;
      }
      .stage-chrome h3 {
        font-family: 'DM Sans', sans-serif;
        font-weight: 700;
        font-size: 1.15rem;
        color: var(--cream);
        margin: 0 0 8px;
      }
      .stage-pill {
        display: inline-block;
        align-self: flex-start;
        font-family: 'DM Sans', sans-serif;
        font-size: 0.62rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding: 3px 9px;
        border-radius: 20px;
        border: 1px solid var(--border);
        color: var(--muted);
        margin-bottom: 10px;
      }
      .stage-pill.accent {
        color: var(--orange);
        border-color: rgba(255, 69, 0, 0.4);
      }
      .stage-chrome p {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.85rem;
        line-height: 1.5;
        /* No opacity dimming here: at 0.85rem it only cost contrast. Use a colour
           token when something needs to recede. */
        color: var(--text);
        margin: 0;
      }
      .stage-locked-note {
        font-family: 'DM Sans', sans-serif;
        font-size: 0.78rem;
        line-height: 1.4;
        color: var(--muted);
        text-align: center;
        border: 1px dashed var(--border);
        border-radius: 10px;
        padding: 10px 12px;
      }

      /* Real st.button widgets (key="stage_cta_0".."stage_cta_2") styled to
         look like each card's CTA, via Streamlit's own st-key-<key> wrapper
         class. Not using [data-testid="stButton"]: verified against the
         installed Streamlit 1.49.1 frontend bundle that testid no longer
         exists in this version. */
      div[class*="st-key-stage_cta_"] button {
        width: 100%;
        border-radius: 10px;
        border: 1px solid var(--border);
        background: var(--bg);
        color: var(--cream);
        font-family: 'DM Sans', sans-serif;
      }
      div[class*="st-key-stage_cta_"] button:hover {
        border-color: var(--orange);
        color: var(--orange);
      }
    </style>

    <div class="stages-eyebrow">Your workflow</div>
    <div class="stages-title">Four stages to your next <em>Reddit post</em>.</div>
    <p class="stages-sub">
      Locol Content AI turns what you know into content that sounds like you.
      Stage 1 is optional — most people start with the Business Survey.
    </p>
    """, unsafe_allow_html=True)

    cols = st.columns(4, gap="medium")
    for i, (col, stage) in enumerate(zip(cols, HOME_STAGES)):
        with col:
            pill_html = ""
            if stage["pill"]:
                variant = "stage-pill accent" if stage["pill_accent"] else "stage-pill"
                pill_html = f'<span class="{variant}">{stage["pill"]}</span>'

            st.markdown(f"""
            <div class="stage-chrome">
              <div class="stage-chrome-top">
                <span class="stage-chrome-icon">{stage['icon']}</span>
                <span class="stage-chrome-index">{stage['index']}</span>
              </div>
              <h3>{stage['title']}</h3>
              {pill_html}
              <p>{stage['description']}</p>
            </div>
            """, unsafe_allow_html=True)

            if stage["target"]:
                if st.button(stage["cta"], key=f"stage_cta_{i}", use_container_width=True):
                    st.switch_page(stage["target"])
            else:
                st.markdown(
                    f'<div class="stage-locked-note">{stage["locked_note"]}</div>',
                    unsafe_allow_html=True,
                )


def _fetch_sidebar_projects():
    """Fetch the project list for the sidebar nav."""
    try:
        response = requests.get(f"{LOCOL_API_URL}/api/get-projects/", headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        st.error(f"Failed to fetch projects ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching projects: {str(e)}")
    return []


def _fetch_sidebar_project_ideas(project_id):
    """Fetch a single project's ideas for the sidebar nav."""
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/get-project-brainstorming-ideas",
            params={"project_id": project_id},
            headers=get_api_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        st.error(f"Failed to fetch project ideas ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching project ideas: {str(e)}")
    return []


def render_home_nav(pg, home_page):
    """Global sidebar: Home link, pinned above the other custom nav sections."""
    with st.sidebar:
        st.markdown("**🏠 Home**")

        on_home_page = (pg.url_path == home_page.url_path)
        if st.button("🏠 Home", key="nav_home", use_container_width=True):
            if on_home_page:
                st.rerun()
            else:
                st.switch_page(home_page)


def render_business_survey_nav(pg, business_survey_page):
    """Global sidebar: expandable list of Business Survey pages.

    Works from any page - clicking a page jumps to that step of the
    Business Survey, switching pages unless already there.
    """
    with st.sidebar:
        header_col, toggle_col = st.columns([4, 1])
        with header_col:
            st.markdown("**📝 Business Survey**")
        with toggle_col:
            is_expanded = st.session_state.get("nav_business_survey_expanded", False)
            if st.button("▼" if is_expanded else "▶", key="nav_toggle_business_survey", help="Show pages", use_container_width=True):
                st.session_state.nav_business_survey_expanded = not is_expanded
                st.rerun()

        if st.session_state.get("nav_business_survey_expanded", False):
            on_survey_page = (pg.url_path == business_survey_page.url_path)
            for i, page in enumerate(get_business_survey_pages()):
                # Same [1, 5] column split as the project button's name_col, so the
                # width matches exactly.
                page_spacer_col, page_button_col = st.columns([1, 5])
                with page_button_col:
                    if st.button(page["title"], key=f"nav_business_page_{i}", use_container_width=True):
                        st.session_state.business_survey_current_page = i
                        if on_survey_page:
                            st.rerun()
                        else:
                            st.switch_page("locol-lib/survey.py")


def _idea_edit_in_progress():
    """True only if the user is genuinely mid-edit (clicked "Edit" and hasn't saved/cancelled)."""
    return st.session_state.get("manual_edit_idea_id") is not None


def render_campaign_projects_nav(pg, project_survey_page):
    """Global sidebar: expandable list of Campaign Projects and their ideas.

    Works from any page - clicking a project/idea switches to the Campaign
    Projects page with that project's data loaded, unless already there.
    """
    with st.sidebar:
        on_project_page = (pg.url_path == project_survey_page.url_path)

        header_col, add_col, refresh_col = st.columns([3, 1, 1])
        with header_col:
            st.markdown("**📁 Campaign Projects**")
        with add_col:
            if st.button("➕", key="nav_add_project", help="Add a new project", use_container_width=True):
                st.session_state.show_create_project = True
                if on_project_page:
                    st.rerun()
                else:
                    st.switch_page("locol-lib/projectSurvey.py")
        with refresh_col:
            if st.button("🔄", key="nav_refresh_projects", help="Refresh project list", use_container_width=True):
                st.session_state.pop("sidebar_nav_projects", None)
                st.rerun()

        if "sidebar_nav_projects" not in st.session_state:
            st.session_state.sidebar_nav_projects = _fetch_sidebar_projects()

        expanded_id = st.session_state.get("nav_expanded_project")

        for project in st.session_state.sidebar_nav_projects:
            pid = project.get("id")
            pname = project.get("name", pid)
            is_expanded = (expanded_id == pid)
            already_here = on_project_page and st.session_state.get("selected_project") == pid

            toggle_col, name_col = st.columns([1, 5])
            with toggle_col:
                if st.button("▼" if is_expanded else "▶", key=f"nav_toggle_{pid}", help="Show ideas"):
                    if is_expanded:
                        st.session_state.nav_expanded_project = None
                    else:
                        st.session_state.nav_expanded_project = pid
                        # Force a fresh fetch next render (e.g. picks up manually-added ideas)
                        st.session_state.setdefault("sidebar_nav_ideas_cache", {}).pop(pid, None)
                    st.rerun()
            with name_col:
                if st.button(pname, key=f"nav_project_{pid}", use_container_width=True):
                    if _idea_edit_in_progress():
                        st.warning("⚠️ Please save or cancel your idea edits before navigating.")
                    else:
                        if st.session_state.get("selected_project") != pid:
                            select_project(pid, pname)
                        st.session_state.current_page = "campaign_insights"
                        st.session_state.pop("scroll_to_modal", None)
                        st.session_state["scroll_to_top"] = True
                        if st.session_state.get("nav_expanded_project") != pid:
                            st.session_state.nav_expanded_project = pid
                            # Force a fresh fetch next render (e.g. picks up manually-added ideas)
                            st.session_state.setdefault("sidebar_nav_ideas_cache", {}).pop(pid, None)
                        if already_here:
                            st.rerun()
                        else:
                            st.switch_page("locol-lib/projectSurvey.py")

            if is_expanded:
                ideas_cache = st.session_state.setdefault("sidebar_nav_ideas_cache", {})
                if pid not in ideas_cache:
                    ideas_cache[pid] = _fetch_sidebar_project_ideas(pid)
                ideas = ideas_cache[pid]

                if not ideas:
                    st.caption("No ideas yet")
                for idea in ideas:
                    idea_id = idea.get("id")
                    idea_title = idea.get("title", "Untitled idea")
                    # Idea button = 90% of the project button's width (name_col is 5/6 of the
                    # row), right-aligned: spacer:button ratio of 1:3 gives 4.5/6 = 0.9 * 5/6.
                    idea_spacer_col, idea_button_col = st.columns([1, 3])
                    with idea_button_col:
                        if st.button(f"　💡 {idea_title}", key=f"nav_idea_{idea_id}", use_container_width=True):
                            if _idea_edit_in_progress():
                                st.warning("⚠️ Please save or cancel your idea edits before navigating.")
                            else:
                                if st.session_state.get("selected_project") != pid:
                                    select_project(pid, pname)
                                st.session_state.navigate_to_idea = idea_id
                                st.session_state.current_page = "campaign_insights"
                                if already_here:
                                    st.rerun()
                                else:
                                    st.switch_page("locol-lib/projectSurvey.py")


def render_settings_and_tools_nav(pg, config_manager_page, find_your_voice_page):
    """Global sidebar: Settings and Tools (Config Manager, Find your voice)."""
    with st.sidebar:
        st.markdown("**⚙️ Settings and Tools**")

        on_config_page = (pg.url_path == config_manager_page.url_path)
        if st.button("⚙️ Config Manager", key="nav_config_manager", use_container_width=True):
            if on_config_page:
                st.rerun()
            else:
                st.switch_page("locol-lib/configManager.py")

        on_voice_page = (pg.url_path == find_your_voice_page.url_path)
        if st.button("🎤 Find your voice", key="nav_find_your_voice", use_container_width=True):
            if on_voice_page:
                st.rerun()
            else:
                st.switch_page("locol-lib/findYourVoice.py")


# Initialize authentication session
init_auth_session()

# Create pages using st.Page
home = st.Page(home_page, title="🏠 Home", icon="🏠", default=True)

# Survey pages (only if authenticated)
business_survey = st.Page("locol-lib/survey.py", title="📝 Business Survey", icon="📝")
project_survey = st.Page("locol-lib/projectSurvey.py", title="🎯 Campaign Projects", icon="🎯")

# Configuration pages
config_manager = st.Page("locol-lib/configManager.py", title="⚙️ Config Manager", icon="⚙️")

# Voice tools pages
find_your_voice = st.Page("locol-lib/findYourVoice.py", title="Find your voice", icon="🎤")

# Create navigation based on authentication status
if st.session_state.authenticated:
    # Show full navigation for authenticated users
    pg = st.navigation({
        "🏠 Main": [home],
        "📋 Survey Tools": [business_survey, project_survey],
        "⚙️ Settings and Tools": [config_manager, find_your_voice]
    })
    render_home_nav(pg, home)
    render_business_survey_nav(pg, business_survey)
    render_campaign_projects_nav(pg, project_survey)
    render_settings_and_tools_nav(pg, config_manager, find_your_voice)
else:
    # Show only home page for unauthenticated users
    pg = st.navigation({
        "🏠 Main": [home]
    })

# Run the selected page
pg.run()