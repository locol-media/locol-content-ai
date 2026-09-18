# projectState.py - shared project loading / session-state helpers
#
# Library module, not a Streamlit page: it defines functions only and makes no
# `st.*` calls at import time, so any page (including main.py, before
# st.set_page_config) can import it safely. Keep it that way - the sidebar nav
# in main.py used to import these from projectSurvey.py, which meant every page
# re-ran that page's top-level code and any breakage there blanked the whole app.
import os
import yaml
import requests
import streamlit as st
from apiClient import LOCOL_API_URL, get_api_headers


def get_project_data(project_id):
    """Get project data from the API"""
    try:
        response = requests.get(f"{LOCOL_API_URL}/api/get-project?id={project_id}", headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to fetch project data: HTTP {response.status_code}")
            return {}
    except requests.exceptions.ConnectionError:
        st.error(f"Could not connect to project server at {LOCOL_API_URL}")
        return {}
    except Exception as e:
        st.error(f"Error fetching project data: {str(e)}")
        return {}


def get_available_question_sets():
    """Get list of available question sets from the question-sets folder.
    Files with project_survey: false are excluded (e.g. business_survey_questions.yaml)."""
    question_sets = []
    question_sets_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'question-sets')

    try:
        for filename in os.listdir(question_sets_dir):
            if filename.endswith('.yaml') or filename.endswith('.yml'):
                yaml_path = os.path.join(question_sets_dir, filename)
                try:
                    with open(yaml_path, 'r', encoding='utf-8') as file:
                        data = yaml.safe_load(file)
                        if isinstance(data, dict) and 'name' in data:
                            if data.get('project_survey', True) is False:
                                continue
                            question_sets.append({
                                'filename': filename,
                                'name': data['name'],
                                'file_path': yaml_path,
                                'additional_instructions': data.get('additional_instructions', '')
                            })
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
                    continue
    except Exception as e:
        print(f"Error accessing question-sets directory: {e}")

    return question_sets


def get_question_set_file_path(question_set_name):
    """Get file path for a specific question set by name"""
    available_question_sets = get_available_question_sets()

    # Find the question set by name
    for qs in available_question_sets:
        if qs['name'] == question_set_name:
            return qs['file_path']

    # Fallback to Default Question Set if not found
    for qs in available_question_sets:
        if qs['name'] == "Default Question Set":
            return qs['file_path']

    # Last resort: return the hardcoded path
    return os.path.join(os.path.dirname(__file__), '..', '..', 'question-sets', 'strategic_questions.yaml')


@st.cache_data
def load_strategic_questions(question_set_name=None):
    """Load strategic questions from YAML file based on question set name"""
    # Get the question set name from project data if not provided
    if question_set_name is None:
        if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
            project_data = get_project_data(st.session_state.selected_project)
            question_set_name = project_data.get('question_set', "Default Question Set")
        else:
            question_set_name = "Default Question Set"

    # Get the file path for this question set
    yaml_path = get_question_set_file_path(question_set_name)

    try:
        with open(yaml_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        st.error(f"Strategic questions file not found at {yaml_path}")
        return {}
    except yaml.YAMLError as e:
        st.error(f"Error parsing YAML file: {e}")
        return {}


def get_project_brainstorming_ideas(project_id):
    """Get brainstorming ideas for a specific project"""
    try:
        response = requests.get(f"{LOCOL_API_URL}/api/get-project-brainstorming-ideas",
                               params={"project_id": project_id},
                               headers=get_api_headers(),
                               timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {}
    except requests.exceptions.ConnectionError:
        st.error(f"Could not connect to server at {LOCOL_API_URL}")
        return {}
    except Exception as e:
        st.error(f"Error fetching brainstorming ideas: {str(e)}")
        return {}


def select_project(project_id, project_name=None):
    """Switch to a project: load its survey/brainstorm data into session state.

    Shared by the project dropdown and the global sidebar nav - callers should
    check `project_id != st.session_state.selected_project` first and call
    `st.rerun()` / `st.switch_page()` afterward as appropriate.
    """
    if project_name is None and st.session_state.dropdown_list is not None:
        item = st.session_state.dropdown_list.get_item_by_id(project_id)
        project_name = item.name if item else project_id

    st.session_state.selected_project = project_id
    # Clear existing survey data first
    st.session_state.strategic_survey_data = {}
    st.session_state.brainstorming_data = None
    # Force show_insights_page()'s fallback fetch to retry for this project, since we just
    # wiped brainstorming_data - otherwise a stale last_checked_project from an earlier visit
    # to this same project blocks the fallback from ever refetching it.
    #
    # This pop is load-bearing, not defensive: show_insights_page() is the ONLY place that
    # loads brainstorm ideas. select_project() deliberately does not fetch them - it used to
    # look as though it did, via an else-branch that could never fire because the endpoint
    # returns a bare list rather than a {"brainstorm_ideas": [...]} dict.
    st.session_state.pop('last_checked_project', None)
    # Load project data when a new project is selected
    project_data = get_project_data(project_id)

    # Update questions config based on project's question set
    question_set_name = project_data.get('question_set', "Default Question Set") if project_data else "Default Question Set"
    st.session_state.questions_config = load_strategic_questions(question_set_name)
    if project_data:
        # Debug: Show what keys are available in project data
        st.write(f"Debug - Project data keys: {list(project_data.keys())}")

        if 'survey_data' in project_data:
            st.session_state.strategic_survey_data = project_data['survey_data']

        # Check for brainstorming ideas in various possible locations
        if 'brainstorming_data' in project_data:
            st.session_state.brainstorming_data = project_data['brainstorming_data']
            st.write(f"Debug - Loaded brainstorming_data")
        elif 'brainstorm_ideas' in project_data:
            # If brainstorm_ideas are stored directly, wrap them in the expected format
            st.session_state.brainstorming_data = {
                "success": True,
                "data": {"brainstorm_ideas": project_data['brainstorm_ideas']},
                "message": "Loaded existing brainstorm ideas"
            }
            st.write(f"Debug - Found brainstorm_ideas directly")
        elif 'llm_response' in project_data:
            st.session_state.brainstorming_data = project_data['llm_response']
            st.write(f"Debug - Loaded llm_response")

        st.success(f"✅ Loaded project data for: {project_name}")
    else:
        st.info(f"📝 No existing data found for: {project_name}")
