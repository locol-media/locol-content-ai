# main.py - Main application file
import streamlit as st
from streamlit_survey import StreamlitSurvey
import json
import os
from datetime import datetime
import time
import requests
import yaml
from uuid_utils import uuid7
from apiClient import (
    LOCOL_API_URL,
    LOCOL_WWW_URL,
    LLM_REQUEST_TIMEOUT,
    LLM_TIMEOUT_DESCRIPTION,
    get_api_headers,
)
from surveyPages import (
    load_business_survey_questions,
    load_business_survey_page_configs,
    get_business_survey_pages,
    canonicalize_option,
)
from surveyRequired import (
    missing_message,
    missing_required,
    page_legend,
    question_label,
)

st.markdown("---")
# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #3498db;
        padding-bottom: 0.5rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.375rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #e7f3ff;
        border: 1px solid #b8daff;
        border-radius: 0.375rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .progress-text {
        text-align: center;
        font-size: 1.1rem;
        color: #2c3e50;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
def init_session_state():
    if 'survey_data' not in st.session_state:
        st.session_state.survey_data = {}
    if 'survey_completed' not in st.session_state:
        st.session_state.survey_completed = False
    if 'business_survey_current_page' not in st.session_state:
        st.session_state.business_survey_current_page = 0
    if 'content_ideas' not in st.session_state:
        st.session_state.content_ideas = {}
    if 'llm_response' not in st.session_state:
        st.session_state.llm_response = None
    if 'llm_loading' not in st.session_state:
        st.session_state.llm_loading = False
    if 'stories_llm_loading' not in st.session_state:
        st.session_state.stories_llm_loading = False
    if 'stories_llm_response' not in st.session_state:
        st.session_state.stories_llm_response = None
    if 'story_ideas_loaded' not in st.session_state:
        st.session_state.story_ideas_loaded = False
    # Auto-load business survey data on first run
    if 'business_survey_loaded' not in st.session_state:
        st.session_state.business_survey_loaded = False

@st.cache_data
def get_existing_survey_value(field_key):
    """Get existing value from survey data"""
    # Check if survey_data exists and is not None
    if (hasattr(st.session_state, 'survey_data') and
        st.session_state.survey_data is not None and
        field_key in st.session_state.survey_data):
        field_data = st.session_state.survey_data[field_key]
        if isinstance(field_data, dict) and 'value' in field_data:
            return field_data['value']
        elif isinstance(field_data, (str, list)):
            return field_data
    return ""

def create_survey_page(survey, page_config):
    """Create a survey page with questions loaded from YAML config"""
    st.markdown(f'<h2 class="section-header">{page_config["title"]}</h2>', unsafe_allow_html=True)
    st.write(page_config["description"])

    st.caption(page_legend(page_config["questions"]))

    for field_key, field_def in page_config["questions"].items():
        # Handle conditional fields (e.g. industry_other only shows when industry == "Other")
        cond = field_def.get("conditional_on")
        if cond:
            current_val = (survey.data.get(cond["field"], {}).get("value")
                           or get_existing_survey_value(cond["field"]))
            if current_val != cond["value"]:
                continue

        q_text = question_label(field_def)
        help_text = field_def.get("help", "")
        q_type = field_def.get("type", "text_area")
        existing = get_existing_survey_value(field_key)

        if q_type == "text_input":
            survey.text_input(q_text, key=field_key, id=field_key, help=help_text, value=existing)
        elif q_type == "text_area":
            survey.text_area(q_text, key=field_key, id=field_key, help=help_text, value=existing)
        elif q_type == "selectbox":
            options = field_def.get("options", [])
            existing = canonicalize_option(existing, options)
            index = options.index(existing) if existing in options else 0
            survey.selectbox(q_text, key=field_key, id=field_key, options=options, index=index)
        elif q_type == "multiselect":
            options = field_def.get("options", [])
            existing = canonicalize_option(existing, options)
            if isinstance(existing, list):
                default = existing
            else:
                default = [existing] if existing and existing in options else []
            survey.multiselect(q_text, key=field_key, id=field_key, options=options, default=default)

def send_to_brainstorm_llm(survey_data, strategic_data=None):
    """Send combined survey data to the brainstorm LLM endpoint"""
    try:
        # Combine both survey datasets
        combined_data = {
            "business_survey": survey_data,
            "strategic_survey": strategic_data or {},
            "timestamp": datetime.now().isoformat(),
            "request_type": "content_brainstorm"
        }
        
        # Send POST request to LLM endpoint
        response = requests.post(
            f"{LOCOL_API_URL}/api/invoke-brainstorm-llm",
            json=combined_data,
            headers=get_api_headers(),
            timeout=LLM_REQUEST_TIMEOUT
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json(),
                "message": "LLM brainstorming completed successfully!"
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "message": "Failed to connect to brainstorm LLM"
            }
            
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Connection refused",
            "message": f"Could not connect to LLM server at {LOCOL_API_URL}. Please ensure the server is running."
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Request timeout",
            "message": f"LLM request timed out after {LLM_TIMEOUT_DESCRIPTION}."
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Unexpected error: {str(e)}"
        }

def get_saved_story_ideas():
    """Retrieve previously saved story ideas from the backend"""
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/get-story-ideas",
            headers=get_api_headers(),
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            ideas = data.get("story_ideas", [])
            if ideas:
                return {"success": True, "data": {"story_ideas": ideas}, "message": "Story ideas loaded!"}
        return None
    except Exception:
        return None

def send_to_story_creation_llm(survey_data):
    """Send business survey data to the story creation LLM endpoint"""
    try:
        payload = {
            "business_survey": survey_data,
            "timestamp": datetime.now().isoformat()
        }
        response = requests.post(
            f"{LOCOL_API_URL}/api/invoke-story-creation-llm",
            json=payload,
            headers=get_api_headers(),
            timeout=LLM_REQUEST_TIMEOUT
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json(), "message": "Story ideas generated!"}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}", "message": "Failed to generate story ideas"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection refused", "message": f"Could not connect to server at {LOCOL_API_URL}."}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timeout", "message": f"Request timed out after {LLM_TIMEOUT_DESCRIPTION}."}
    except Exception as e:
        return {"success": False, "error": str(e), "message": f"Unexpected error: {str(e)}"}

def get_strategic_survey_data():
    """Get strategic survey data from session state if available"""
    return getattr(st.session_state, 'strategic_survey_data', {})

def generate_business_survey_summary(survey_data):
    """Copy all business survey answers into a formatted text block."""
    if not survey_data:
        return ""

    # Build field_key -> question text from the YAML config
    questions_config = load_business_survey_questions()
    question_labels = {}
    for category, questions in questions_config.items():
        if not isinstance(questions, dict):
            continue
        for field_key, field_def in questions.items():
            if isinstance(field_def, dict) and 'question' in field_def:
                question_labels[field_key] = field_def['question']

    lines = []
    for field_key, field_data in survey_data.items():
        val = field_data.get('value', '') if isinstance(field_data, dict) else field_data
        if not val or (isinstance(val, list) and not val):
            continue
        if isinstance(val, list):
            val = ', '.join(str(v) for v in val)
        label = question_labels.get(field_key, field_key.replace('_', ' ').title())
        lines.append(f"{label}: {val}")

    return "\n\n".join(lines)

def create_story_project(project_name, summary_text, skill_content):
    """Create a new project pre-filled with Generated Story survey data."""
    try:
        # Fetch existing projects
        response = requests.get(f"{LOCOL_API_URL}/api/get-projects", headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            existing = response.json()
        else:
            existing = []

        # Build new project item
        now = datetime.now().isoformat()
        new_id = str(uuid7())
        new_item = {"id": new_id, "name": project_name, "parent": None,
                    "create_datetime": now, "replace_datetime": now}
        existing.append(new_item)

        # Persist updated project list
        persist_resp = requests.post(
            f"{LOCOL_API_URL}/api/persist-projects",
            json={"dropdownList": existing},
            headers=get_api_headers(),
            timeout=10
        )
        if persist_resp.status_code != 200:
            return None

        # Save pre-filled Generated Story survey data
        survey_payload = {
            "project_id": new_id,
            "survey_type": "project_survey",
            "survey_data": {
                "q1": {"value": summary_text},
                "q2": {"value": skill_content},
            },
            "question_set": "Generated Story",
            "timestamp": now,
        }
        save_resp = requests.post(
            f"{LOCOL_API_URL}/api/save-project",
            json=survey_payload,
            headers=get_api_headers(),
            timeout=10
        )
        if save_resp.status_code == 200:
            return new_id
        return None

    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None

def save_business_survey_data(survey_data):
    """Save business survey data to business_survey table"""
    try:
        payload = {
            "survey_data": survey_data,
            "timestamp": datetime.now().isoformat()
        }
        response = requests.post(f"{LOCOL_API_URL}/api/save-business-survey", json=payload, headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            return {"success": True, "message": "Business survey saved successfully!"}
        else:
            return {"success": False, "message": f"Save failed: HTTP {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"Could not connect to server at {LOCOL_API_URL}"}
    except Exception as e:
        return {"success": False, "message": f"Error saving business survey: {str(e)}"}

def get_business_survey_data():
    """Get business survey data from the API"""
    try:
        response = requests.get(f"{LOCOL_API_URL}/api/get-business-survey", headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to fetch business survey data: HTTP {response.status_code}")
            return {}
    except requests.exceptions.ConnectionError:
        st.error(f"Could not connect to server at {LOCOL_API_URL}")
        return {}
    except Exception as e:
        st.error(f"Error fetching business survey data: {str(e)}")
        return {}

def main():
    init_session_state()
    
    # Auto-load business survey data if not already loaded
    if not st.session_state.business_survey_loaded:
        business_data = get_business_survey_data()
        if business_data and 'survey_data' in business_data and business_data['survey_data']:
            loaded_data = business_data['survey_data']
            st.session_state.survey_data = loaded_data
            # Pre-populate StreamlitSurvey's internal state so register() finds
            # non-None values and sets st.session_state[widget_key] before rendering.
            # Without this, selectboxes default to index 0 (placeholder) in new sessions.
            survey_data_key = "__streamlit-survey-data_Business Content Discovery Survey"
            if survey_data_key not in st.session_state:
                # Answers saved before an option was respelled (e.g. the en dash in
                # "1–3 years") must be mapped onto the current option text here — a
                # session-state value absent from options makes the widget raise.
                option_map = {
                    fk: fd["options"]
                    for page in get_business_survey_pages()
                    for fk, fd in page["questions"].items()
                    if "options" in fd
                }
                st.session_state[survey_data_key] = {
                    k: {'value': canonicalize_option(v, option_map.get(k, [])), 'widget_key': k}
                    for k, v in loaded_data.items()
                    if v is not None
                }
        st.session_state.business_survey_loaded = True
    
    st.markdown('<h1 class="main-header">🚀 Business Content Discovery Tool</h1>', unsafe_allow_html=True)
    
    # Show the survey directly without internal navigation
    show_survey_page()

def show_survey_page():
    """Display the multi-step survey"""
    survey = StreamlitSurvey("Business Content Discovery Survey")
    survey_pages = get_business_survey_pages()

    # Survey progress
    total_pages = len(survey_pages)
    current_page = st.session_state.business_survey_current_page

    st.markdown(f'<div class="progress-text">Survey Progress: {current_page + 1} of {total_pages}</div>',
                unsafe_allow_html=True)

    # Progress bar
    progress = (current_page + 1) / total_pages
    st.progress(progress)

    # Display current survey page
    if current_page < total_pages:
        page_config = survey_pages[current_page]
        create_survey_page(survey, page_config)
        
        # Save button for current page
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**Current Page:** {page_config['title']}")
        with col2:
            if st.button("💾 Save Page", use_container_width=True, type="secondary"):
                # Initialize survey_data if it's None
                if st.session_state.survey_data is None:
                    st.session_state.survey_data = {}
                # Update session data with current survey data
                st.session_state.survey_data.update(survey.data)
                # Save to business survey table
                result = save_business_survey_data(st.session_state.survey_data)
                if result["success"]:
                    st.success("✅ Page saved successfully!")
                else:
                    st.error(f"❌ Save failed: {result['message']}")
        
        # Navigation buttons
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if current_page > 0:
                if st.button("⬅️ Previous", use_container_width=True):
                    st.session_state.business_survey_current_page -= 1
                    st.rerun()
        
        with col3:
            if current_page < total_pages - 1:
                if st.button("Next ➡️", use_container_width=True, type="primary"):
                    # Validate required fields for current page
                    missing = missing_required_questions(survey.data, current_page)
                    if not missing:
                        # Initialize survey_data if it's None
                        if st.session_state.survey_data is None:
                            st.session_state.survey_data = {}
                        st.session_state.survey_data.update(survey.data)
                        st.session_state.business_survey_current_page += 1
                        st.rerun()
                    else:
                        st.error(missing_message(missing, "proceeding"))
            else:
                if st.button("💾 Save Business Survey", use_container_width=True, type="primary"):
                    missing = missing_required_questions(survey.data, current_page)
                    if not missing:
                        # Initialize survey_data if it's None
                        if st.session_state.survey_data is None:
                            st.session_state.survey_data = {}
                        st.session_state.survey_data.update(survey.data)
                        st.session_state.survey_completed = True
                        # Auto-save on completion
                        result = save_business_survey_data(st.session_state.survey_data)
                        if result["success"]:
                            st.success("✅ Survey completed and saved! Next: press ✨ Generate Story Ideas below "
                                       "to turn your background into Reddit story ideas.")
                        else:
                            st.warning("✅ Survey completed but save failed. Please use the Save Page button.")
                    else:
                        st.error(missing_message(missing, "completing the survey"))
    
        # Story creation button — last page only
        if current_page == total_pages - 1:
            if not st.session_state.story_ideas_loaded:
                saved = get_saved_story_ideas()
                if saved:
                    st.session_state.stories_llm_response = saved
                st.session_state.story_ideas_loaded = True
            st.markdown("---")
            st.markdown("### 📖 Generate Story Ideas")
            st.write("Use your skills and hobbies to generate personal story ideas for your target audience.")
            if st.button("✨ Generate Story Ideas", type="primary", use_container_width=True):
                if st.session_state.survey_data is None:
                    st.session_state.survey_data = {}
                st.session_state.survey_data.update(survey.data)
                st.session_state.stories_llm_loading = True
                st.rerun()

            if st.session_state.stories_llm_loading:
                with st.spinner("🤖 Generating story ideas from your background..."):
                    result = send_to_story_creation_llm(st.session_state.survey_data)
                    st.session_state.stories_llm_response = result
                    st.session_state.stories_llm_loading = False
                    st.rerun()

            if st.session_state.stories_llm_response:
                st.markdown("---")
                if st.session_state.stories_llm_response["success"]:
                    st.success("✅ Story ideas generated!")
                    ideas = st.session_state.stories_llm_response.get("data", {}).get("story_ideas", [])
                    for i, idea in enumerate(ideas):
                        with st.expander(f"📖 {idea.get('title', 'Story Idea')}"):
                            st.write(f"**Angle:** {idea.get('story_angle', '')}")
                            st.write(f"**Why relevant:** {idea.get('why_relevant', '')}")
                            topics = idea.get('reddit_post_topics', [])
                            if topics:
                                st.write("**Reddit post topics:**")
                                if isinstance(topics, list):
                                    for topic in topics:
                                        title = topic.get('topic_title', '')
                                        relevance = topic.get('relevance_to_story', '')
                                        subs = topic.get('subreddits', [])
                                        subs_str = ', '.join(subs) if isinstance(subs, list) else subs
                                        st.write(f"&nbsp;&nbsp;**{title}** — {relevance} *(subreddits: {subs_str})*")
                                else:
                                    st.write(topics)
                            cols = st.columns(2)
                            cols[0].caption(f"Emotion: {idea.get('target_emotion', '')}")
                            cols[1].caption(f"Source: {idea.get('source', '')}")
                            if st.button("🚀 Create Project", key=f"create_project_{i}"):
                                idea_title = idea.get('title', f'Story Idea {i + 1}')
                                summary = generate_business_survey_summary(st.session_state.survey_data)
                                angle = idea.get('story_angle', '')
                                why_relevant = idea.get('why_relevant', '')
                                skill_content = '\n\n'.join(filter(None, [angle, why_relevant]))
                                result = create_story_project(idea_title, summary, skill_content)
                                if result:
                                    st.success(f"✅ Project '{idea_title}' created! Open the Projects page to continue.")
                                else:
                                    st.error("Failed to create project. Check your connection.")
                else:
                    st.error(f"❌ {st.session_state.stories_llm_response['message']}")
                if st.button("🗑️ Clear Story Ideas"):
                    st.session_state.stories_llm_response = None
                    st.rerun()

def missing_required_questions(survey_data, page_index):
    """Return the question text of each unanswered required field on the page."""
    pages = get_business_survey_pages()
    if page_index >= len(pages):
        return []
    return missing_required(pages[page_index]["questions"], survey_data)

if __name__ == "__main__":
    main()

