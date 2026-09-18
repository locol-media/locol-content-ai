# projectSurvey.py - Campaign Projects
import streamlit as st
import streamlit.components.v1 as components
from streamlit_survey import StreamlitSurvey
import json
from datetime import datetime
import time
import requests
import yaml
import os
import pandas as pd
from uuid_utils import uuid7
from apiClient import (
    LOCOL_API_URL,
    LOCOL_WWW_URL,
    LLM_REQUEST_TIMEOUT,
    LLM_TIMEOUT_DESCRIPTION,
    get_api_headers,
)
from htmlSanitize import sanitize_generated_html
from generate_items_models import MAX_IDEAS_PER_BATCH
from voices import voice_selectbox
from projectState import (
    get_project_data,
    get_available_question_sets,
    load_strategic_questions,
    get_project_brainstorming_ideas,
    select_project,
)
from surveyRequired import (
    missing_message,
    missing_required,
    page_legend,
    question_label,
)

CONTENT_TYPE_OPTIONS = [
    "Blog Post", "Social Media Post", "Video", "Email", "Newsletter",
    "White Paper", "Case Study", "Infographic", "Podcast", "Webinar"
]

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #e74c3c;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #e74c3c;
        padding-bottom: 0.5rem;
    }
    .question-category {
        background-color: #f8f9fa;
        border-left: 4px solid #e74c3c;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 0 0.375rem 0.375rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
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

# Global dropdown list for projects
global_dropdown_list = None

class DropDownItem:
    """Individual dropdown item"""
    def __init__(self, id, name,parent=None, create_datetime=None, replace_datetime=None):
        self.id = id
        self.name = name
        self.parent = parent
        self.create_datetime = create_datetime or datetime.now().isoformat()
        self.replace_datetime = replace_datetime or datetime.now().isoformat()
class DropDowndropdownList:
    """Dropdown list model"""
    def __init__(self):
        self.items = []
    
    def add_item(self, name):
        """Add new item to the list"""
        # Generate new UUID v7 ID
        new_id = str(uuid7())
        new_item = DropDownItem(
            id=new_id,
            name=name,
            parent=None,
            create_datetime=datetime.now().isoformat(),
            replace_datetime=datetime.now().isoformat()
        )
        self.items.append(new_item)
        return new_item
    
    def get_names(self):
        """Get list of names for dropdown"""
        return [item.name for item in self.items]
    
    def get_item_by_name(self, name):
        """Get item by name"""
        for item in self.items:
            if item.name == name:
                return item
        return None

    def get_item_by_id(self, item_id):
        """Get item by ID"""
        for item in self.items:
            if item.id == item_id:
                return item
        return None
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "dropdownList": [
                {
                    "id": item.id,
                    "name": item.name,
                    "parent": item.parent,
                    "create_datetime": item.create_datetime,
                    "replace_datetime": item.replace_datetime
                }
                for item in self.items
        ]}
    
    @classmethod
    def from_dict(cls, data):
        """Create from dictionary"""
        dropdown_list = cls()
        #if "items" in data:
        for item_data in data:
            item = DropDownItem(
                id=item_data.get("id"),
                name=item_data.get("name"),
                parent=item_data.get("parent"),
                create_datetime=item_data.get("create_datetime"),
                replace_datetime=item_data.get("replace_datetime")
            )
            dropdown_list.items.append(item)
        return dropdown_list

def get_projects():
    """Get dropdown list from API and store globally"""
    global global_dropdown_list
    
    try:
        response = requests.get(f"{LOCOL_API_URL}/api/get-projects", headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            data = response.json()
            global_dropdown_list = DropDowndropdownList.from_dict(data)
            return global_dropdown_list
        else:
            st.error(f"Failed to fetch projects: HTTP {response.status_code}")
            # Initialize empty list if API fails
            if global_dropdown_list is None:
                global_dropdown_list = DropDowndropdownList()
            return global_dropdown_list
    except requests.exceptions.ConnectionError:
        st.error(f"Could not connect to project server at {LOCOL_API_URL}")
        # Initialize empty list if connection fails
        if global_dropdown_list is None:
            global_dropdown_list = DropDowndropdownList()
        return global_dropdown_list
    except Exception as e:
        st.error(f"Error fetching projects: {str(e)}")
        if global_dropdown_list is None:
            global_dropdown_list = DropDowndropdownList()
        return global_dropdown_list

def convert_survey_data_keys(survey_data, project_id):
    """Convert project-specific keys back to original question keys"""
    converted_data = {}
    suffix = f"_{project_id}"
    
    for key, value in survey_data.items():
        if key.endswith(suffix):
            # Remove the project ID suffix to get the original question key
            original_key = key[:-len(suffix)]
            converted_data[original_key] = value
        else:
            # Keep keys that don't have the project suffix
            converted_data[key] = value
    
    return converted_data

def save_project_data(project_id, survey_type, survey_data, question_set=None):
    """Save survey data to the project"""
    try:
        payload = {
            "project_id": project_id,
            "survey_type": survey_type,
            "survey_data": survey_data,
            "question_set": question_set,
            "timestamp": datetime.now().isoformat()
        }
        response = requests.post(f"{LOCOL_API_URL}/api/save-project", json=payload, headers=get_api_headers(), timeout=10)
        if response.status_code == 200:
            return {"success": True, "message": "Project saved successfully!"}
        else:
            return {"success": False, "message": f"Save failed: HTTP {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"Could not connect to project server at {LOCOL_API_URL}"}
    except Exception as e:
        return {"success": False, "message": f"Error saving project: {str(e)}"}

def create_new_project(project_name, question_set_name):
    """Create a new project by adding to dropdown list and persisting"""
    try:
        # Ensure we have a dropdown list in session state
        if st.session_state.dropdown_list is None:
            st.session_state.dropdown_list = DropDowndropdownList()
        
        # Add new project to session state dropdown list
        new_item = st.session_state.dropdown_list.add_item(project_name)
        
        # Persist the updated dropdown list to the API
        payload = st.session_state.dropdown_list.to_dict()
        response = requests.post(f"{LOCOL_API_URL}/api/persist-projects", json=payload, headers=get_api_headers(), timeout=10)
        
        if response.status_code == 200:
            # Save the question set for this project
            project_data = {}
            save_result = save_project_data(new_item.id, "project_survey", project_data, question_set_name)
            if not save_result["success"]:
                st.warning(f"Project created but failed to save question set: {save_result['message']}")

            return {
                "id": new_item.id,
                "name": new_item.name,
                "parent": new_item.parent,
                "create_datetime": new_item.create_datetime,
                "replace_datetime": new_item.replace_datetime
            }
        else:
            # Remove the item from local list if persist failed
            st.session_state.dropdown_list.items.pop()
            st.error(f"Failed to persist project: HTTP {response.status_code}")
            return None
            
    except requests.exceptions.ConnectionError:
        # Remove the item from local list if connection failed
        if st.session_state.dropdown_list and st.session_state.dropdown_list.items:
            st.session_state.dropdown_list.items.pop()
        st.error(f"Could not connect to project server at {LOCOL_API_URL}")
        return None
    except Exception as e:
        # Remove the item from local list if error occurred
        if st.session_state.dropdown_list and st.session_state.dropdown_list.items:
            st.session_state.dropdown_list.items.pop()
        st.error(f"Error creating project: {str(e)}")
        return None

# Load strategic questions from YAML
@st.cache_data
def load_page_configs(config_file: str = 'page_configs.yaml'):
    """Load page configurations from YAML file.

    config_file comes from the page_configs_file key of a question-set YAML (see
    get_page_configs_file_from_questions), so it is always resolved relative to the
    question-sets folder and must stay inside it. Absolute paths and anything that
    escapes via .. or a symlink are rejected.
    """
    question_sets_root = os.path.realpath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'question-sets')
    )

    if os.path.isabs(config_file):
        st.error(f"Page configs file must be a path inside question-sets, got absolute path: {config_file}")
        return {}

    yaml_path = os.path.realpath(os.path.join(question_sets_root, config_file))
    if not yaml_path.startswith(question_sets_root + os.sep):
        st.error(f"Page configs file resolves outside of question-sets: {config_file}")
        return {}

    try:
        with open(yaml_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        st.error(f"Page configs file not found at {yaml_path}")
        return {}
    except yaml.YAMLError as e:
        st.error(f"Error parsing YAML file: {e}")
        return {}

def get_page_configs_file_from_questions():
    """Get the page configs file reference from strategic questions YAML"""
    # Get question set name for current project
    question_set_name = None
    if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
        project_data = get_project_data(st.session_state.selected_project)
        question_set_name = project_data.get('question_set', "Default Question Set")

    questions_data = load_strategic_questions(question_set_name)
    page_configs_file = questions_data.get('page_configs_file', 'page-configs/page_configs.yaml')
    return page_configs_file

# Initialize session state
def init_session_state():
    if 'strategic_survey_data' not in st.session_state:
        st.session_state.strategic_survey_data = {}
    if 'strategic_survey_completed' not in st.session_state:
        st.session_state.strategic_survey_completed = False
    if 'current_strategic_page' not in st.session_state:
        st.session_state.current_strategic_page = 0
    if 'strategic_insights' not in st.session_state:
        st.session_state.strategic_insights = {}
    if 'brainstorming_data' not in st.session_state:
        st.session_state.brainstorming_data = None
    if 'strategic_llm_loading' not in st.session_state:
        st.session_state.strategic_llm_loading = False
    if 'questions_config' not in st.session_state:
        # Initialize with default question set, will be updated when project is selected
        st.session_state.questions_config = load_strategic_questions("Default Question Set")
    if 'selected_project' not in st.session_state:
        st.session_state.selected_project = None
    if 'dropdown_list' not in st.session_state:
        st.session_state.dropdown_list = None
    if 'show_create_project' not in st.session_state:
        st.session_state.show_create_project = False

def get_strategic_survey_pages():
    """Generate survey pages configuration from YAML questions"""
    questions_config = st.session_state.questions_config

    # Get the page configs file reference from strategic questions
    page_configs_file = get_page_configs_file_from_questions()
    page_configs = load_page_configs(page_configs_file)

    pages = []

    # Debug information
    if not questions_config:
        print("DEBUG: questions_config is empty or None")
        return pages

    if not page_configs:
        print("DEBUG: page_configs is empty or None")
        return pages

    for category, questions in questions_config.items():
        # Skip metadata fields that are not question categories
        if category in ['page_configs_file', 'name']:
            continue

        print(f"DEBUG: Processing category '{category}', questions: {list(questions.keys()) if isinstance(questions, dict) else 'Not a dict'}")

        if category in page_configs:
            page_config = page_configs[category].copy()
            page_config["category"] = category

            # Add category info to each question from page_config instead of YAML
            questions_with_category = {}
            for question_key, question_data in questions.items():
                question_with_category = question_data.copy()
                question_with_category["category"] = page_configs[category]["title"]
                questions_with_category[question_key] = question_with_category

            page_config["questions"] = questions_with_category
            pages.append(page_config)
            print(f"DEBUG: Added page for category '{category}'")
        else:
            print(f"DEBUG: Category '{category}' not found in page_configs. Available: {list(page_configs.keys())}")

    print(f"DEBUG: Total pages created: {len(pages)}")
    return pages

def create_strategic_survey_page(survey, page_config):
    """Create a strategic survey page with questions from YAML"""
    st.markdown(f'<div class="question-category">', unsafe_allow_html=True)
    st.markdown(f'<h2 class="section-header">{page_config["title"]}</h2>', unsafe_allow_html=True)
    st.write(page_config["description"])
    st.markdown('</div>', unsafe_allow_html=True)

    # Iterate through questions in this category
    questions = page_config.get("questions", {})
    st.caption(page_legend(questions))
    for question_key, question_data in questions.items():
        # Get existing value from session state if available
        existing_value = ""
        if question_key in st.session_state.strategic_survey_data:
            field_data = st.session_state.strategic_survey_data[question_key]
            if isinstance(field_data, dict) and 'value' in field_data:
                existing_value = field_data['value']
            elif isinstance(field_data, str):
                existing_value = field_data
        
        # Create unique key for each field that includes project ID
        field_key = f"{question_key}_{st.session_state.selected_project}"
        
        # Pre-populate the session state with the existing value if not already set
        if field_key not in st.session_state and existing_value:
            st.session_state[field_key] = existing_value
        
        height = question_data.get("height")
        survey.text_area(
            question_label(question_data),
            key=field_key,
            id=question_key,
            help=question_data.get("help", ""),
            value=existing_value,
            **({"height": height} if height else {})
        )

def get_question_from_config(field_key, questions_config):
    """Get question text from YAML config using field key. Uses llm_prompt if available, otherwise question"""
    for category, questions in questions_config.items():
        if field_key in questions:
            question_data = questions[field_key]
            # Use llm_prompt if available, otherwise fall back to question
            if 'llm_prompt' in question_data:
                return question_data['llm_prompt']
            else:
                return question_data.get("question", field_key)
    return field_key

def get_category_from_config(field_key, questions_config):
    """Get category from YAML config using field key"""
    for category, questions in questions_config.items():
        if field_key in questions:
            return category
    return "uncategorized"

def send_to_brainstorm_llm(strategic_data, business_survey_data=None):
    """Send combined survey data to the brainstorm LLM endpoint"""
    try:
        # Enrich strategic data with question text
        enriched_strategic_data = {}
        questions_config = st.session_state.questions_config

        # Get additional instructions from the question set
        additional_instructions = questions_config.get('additional_instructions', '')

        for field_key, field_data in strategic_data.items():
            if isinstance(field_data, dict) and 'value' in field_data:
                # Find question text from YAML config
                question_text = get_question_from_config(field_key, questions_config)
                category = get_category_from_config(field_key, questions_config)
                
                enriched_strategic_data[field_key] = {
                    "question": question_text,
                    "value": field_data['value'],
                    "category": category
                }
            else:
                enriched_strategic_data[field_key] = field_data
        
        # Extract only value fields from business survey data
        business_survey_values = {}
        if business_survey_data:
            for key, field_data in business_survey_data.items():
                if isinstance(field_data, dict) and 'value' in field_data:
                    business_survey_values[key] = field_data['value']
                else:
                    business_survey_values[key] = field_data
        
        # Combine both survey datasets
        combined_data = {
            "project_id": st.session_state.selected_project,
            "business_survey": business_survey_values,
            "strategic_survey": enriched_strategic_data,
            "additional_instructions": additional_instructions,
            "timestamp": datetime.now().isoformat(),
            "request_type": "strategic_brainstorm"
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
                "message": "Strategic AI brainstorming completed successfully!"
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

def get_business_survey_data():
    """Get business survey data from session state if available, otherwise fetch from API"""
    survey_data = getattr(st.session_state, 'survey_data', {})
    
    if not survey_data:
        try:
            response = requests.get(f"{LOCOL_API_URL}/api/get-business-survey", headers=get_api_headers(), timeout=10)
            if response.status_code == 200:
                survey_data = response.json()
                st.session_state.survey_data = survey_data
            else:
                st.error(f"Failed to fetch business survey data: HTTP {response.status_code}")
                survey_data = {}
        except requests.exceptions.ConnectionError:
            st.error(f"Could not connect to server at {LOCOL_API_URL}")
            survey_data = {}
        except Exception as e:
            st.error(f"Error fetching business survey data: {str(e)}")
            survey_data = {}
    
    return survey_data

def invalidate_sidebar_ideas(project_id, expand=False):
    """Force the sidebar nav to re-fetch this project's ideas on the next render.

    The sidebar renders its 💡 entries from project_brainstorm_ideas via a
    per-project cache (see render_campaign_projects_nav in main.py), so any
    write to that table has to drop the cached copy or the nav goes stale.
    """
    st.session_state.setdefault("sidebar_nav_ideas_cache", {}).pop(project_id, None)
    if expand:
        st.session_state.nav_expanded_project = project_id


def save_brainstorming_ideas_to_db(project_id, brainstorm_data):
    """Save changes to brainstorming ideas back to the database"""
    try:
        # Extract ideas from brainstorm_data structure
        if isinstance(brainstorm_data, dict) and 'brainstorm_ideas' in brainstorm_data:
            ideas_list = brainstorm_data['brainstorm_ideas']
        else:
            # Handle DataFrame format (legacy support)
            ideas_list = []
            for _, row in brainstorm_data.iterrows():
                ideas_list.append({
                    'id': row['ID'],
                    'title': row['Title'],
                    'description': row['Description'],
                    'content_type': row['Content Type'],
                    'platform': row['Platform'],
                    'goal': row['Goal']
                })
        
        payload = {
            "project_id": project_id,
            "brainstorm_ideas": ideas_list,
            "timestamp": datetime.now().isoformat()
        }
        
        response = requests.post(f"{LOCOL_API_URL}/api/save-project-brainstorming-ideas", 
                                json=payload, 
                                headers=get_api_headers(),
                                timeout=10)
        if response.status_code == 200:
            return {"success": True, "message": "Ideas saved successfully"}
        else:
            return {"success": False, "message": f"Save failed: HTTP {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": f"Could not connect to server at {LOCOL_API_URL}"}
    except Exception as e:
        return {"success": False, "message": f"Error saving ideas: {str(e)}"}

def generate_strategic_insights(survey_data):
    """Generate insights based on strategic survey responses"""
    insights = {
        'emotional_triggers': [],
        'positioning_opportunities': [],
        'audience_expansion': [],
        'timing_strategies': [],
        'competitive_advantages': []
    }
    
    # Analyze emotional triggers
    problem_solving = survey_data.get('problem_solving', {}).get('value', '')
    customer_story = survey_data.get('customer_story', {}).get('value', '')
    
    if problem_solving:
        insights['emotional_triggers'].append(f"Origin story: {problem_solving[:100]}...")
    if customer_story:
        insights['emotional_triggers'].append(f"Impact story: {customer_story[:100]}...")
    
    # Analyze positioning opportunities
    unique_aspect = survey_data.get('unique_aspect', {}).get('value', '')
    wrong_assumptions = survey_data.get('wrong_assumptions', {}).get('value', '')
    
    if unique_aspect:
        insights['positioning_opportunities'].append(f"Untapped advantage: {unique_aspect[:100]}...")
    if wrong_assumptions:
        insights['positioning_opportunities'].append(f"Myth-busting opportunity: {wrong_assumptions[:100]}...")
    
    # Analyze audience expansion
    unexpected_customers = survey_data.get('unexpected_customers', {}).get('value', '')
    customer_obsessions = survey_data.get('customer_obsessions', {}).get('value', '')
    
    if unexpected_customers:
        insights['audience_expansion'].append(f"Hidden segment: {unexpected_customers[:100]}...")
    if customer_obsessions:
        insights['audience_expansion'].append(f"Brand affinity insights: {customer_obsessions[:100]}...")
    
    # Analyze timing strategies
    customer_stress = survey_data.get('customer_stress', {}).get('value', '')
    urgency_drivers = survey_data.get('urgency_drivers', {}).get('value', '')
    
    if customer_stress:
        insights['timing_strategies'].append(f"Current pain point: {customer_stress[:100]}...")
    if urgency_drivers:
        insights['timing_strategies'].append(f"Urgency trigger: {urgency_drivers[:100]}...")
    
    # Analyze competitive advantages
    resource_advantage = survey_data.get('resource_advantage', {}).get('value', '')
    secret_sauce = survey_data.get('secret_sauce', {}).get('value', '')
    
    if resource_advantage:
        insights['competitive_advantages'].append(f"Agility advantage: {resource_advantage[:100]}...")
    if secret_sauce:
        insights['competitive_advantages'].append(f"Hidden capability: {secret_sauce[:100]}...")
    
    return insights

def show_project_selector():
    """Display the create-project form when triggered from the sidebar"""
    global global_dropdown_list

    # New project creation form
    if st.session_state.show_create_project:
        with st.expander("➕ Create New Project", expanded=True):
            project_name = st.text_input("Project Name:", key="new_project_name")

            # Question Set dropdown
            available_question_sets = get_available_question_sets()
            if available_question_sets:
                question_set_names = [qs['name'] for qs in available_question_sets]
                selected_question_set = st.selectbox(
                    "Question Set:",
                    options=question_set_names,
                    key="new_project_question_set",
                    help="Select the question set to use for this project"
                )
            else:
                st.warning("No question sets found in the question-sets folder")
                selected_question_set = None

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Create Project", type="primary", use_container_width=True):
                    if project_name and selected_question_set:
                        new_project = create_new_project(project_name, selected_question_set)
                        if new_project:
                            st.success(f"✅ Created project: {project_name}")
                            # Update session state with the updated global list
                            st.session_state.dropdown_list = global_dropdown_list
                            st.session_state.selected_project = new_project.get('id')
                            # Clear existing survey data for the new empty project
                            st.session_state.strategic_survey_data = {}
                            st.session_state.brainstorming_data = None
                            st.session_state.questions_config = load_strategic_questions(selected_question_set)
                            st.session_state.show_create_project = False
                            # Force the global sidebar nav to refetch so the new project appears
                            st.session_state.pop("sidebar_nav_projects", None)
                            st.rerun()
                    else:
                        if not project_name:
                            st.error("Please enter a project name")
                        if not selected_question_set:
                            st.error("Please select a question set")

            with col2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.show_create_project = False
                    st.rerun()
    
    st.markdown("---")

def main():
    init_session_state()

    if st.session_state.dropdown_list is None:
        st.session_state.dropdown_list = get_projects()

    is_creating_project = st.session_state.show_create_project

    if is_creating_project:
        st.markdown('<h1 class="main-header">➕ Add New Project</h1>', unsafe_allow_html=True)
    else:
        project_name = None
        if st.session_state.selected_project:
            selected_item = st.session_state.dropdown_list.get_item_by_id(st.session_state.selected_project)
            project_name = selected_item.name if selected_item else None

        st.markdown(f'<h1 class="main-header">🎯 {project_name or "Campaign Projects"}</h1>', unsafe_allow_html=True)

    if st.session_state.pop("scroll_to_top", False):
        # Streamlit scrolls its own inner content container (data-testid="stMain"),
        # not the browser window - window.scrollTo() has no visible effect.
        # The nonce forces the iframe's srcdoc to differ from any previous render, since
        # browsers won't reload (and therefore won't re-run the script in) an <iframe>
        # whose content is byte-identical to what's already mounted.
        components.html(f"""
            <script>
                // nonce: {time.time()}
                setTimeout(function() {{
                    try {{
                        const mainEl = window.parent.document.querySelector('[data-testid="stMain"]');
                        console.log("[scroll_to_top] stMain found?", mainEl);
                        if (mainEl) {{
                            mainEl.scrollTo({{top: 0, behavior: "smooth"}});
                        }} else {{
                            window.parent.scrollTo({{top: 0, behavior: "smooth"}});
                        }}
                        console.log("[scroll_to_top] scroll called OK");
                    }} catch (e) {{
                        console.error("[scroll_to_top] error:", e);
                    }}
                }}, 100);
            </script>
        """, height=1)

    show_project_selector()

    if is_creating_project:
        return

    # Initialize navigation state
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "strategic_survey"

    # Display the selected page
    if st.session_state.current_page == "strategic_survey":
        show_strategic_survey_page()
    elif st.session_state.current_page == "campaign_insights":
        show_insights_page()

def show_strategic_survey_page():
    """Display the strategic multi-step survey"""
    # Check if project is selected
    if not st.session_state.selected_project:
        st.warning("⚠️ Please select a project first to save your survey responses, or create a new project via the sidebar.")
        return
    
    # Create survey with project-specific key to ensure it refreshes when project changes
    survey_key = f"Strategic Campaign Discovery Survey - {st.session_state.selected_project}"
    survey = StreamlitSurvey(survey_key)
    
    # Get dynamic survey pages
    survey_pages = get_strategic_survey_pages()
    
    # Survey progress
    total_pages = len(survey_pages)
    current_page = st.session_state.current_strategic_page

    # Check if we have any pages
    if total_pages == 0:
        st.error("❌ No survey pages found. Please check that the question set is properly configured.")
        st.info("Debug info:")
        st.write(f"Questions config keys: {list(st.session_state.questions_config.keys()) if st.session_state.questions_config else 'None'}")
        return

    st.markdown(f'<div class="progress-text">Strategic Discovery Progress: {current_page + 1} of {total_pages}</div>',
                unsafe_allow_html=True)

    # Progress bar
    progress = (current_page + 1) / total_pages
    st.progress(progress)
    
    # Display current survey page
    if current_page < total_pages:
        page_config = survey_pages[current_page]
        create_strategic_survey_page(survey, page_config)
        
        # Save button for current page
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**Current Page:** {page_config['title']}")
        with col2:
            if st.button("💾 Save Page", use_container_width=True, type="secondary"):
                # Update session data with current survey data
                st.session_state.strategic_survey_data.update(survey.data)
                # Convert survey data keys and save to project
                converted_data = convert_survey_data_keys(survey.data, st.session_state.selected_project)
                # Get question set for this project
                project_data = get_project_data(st.session_state.selected_project)
                question_set_name = project_data.get('question_set') if project_data else None
                result = save_project_data(st.session_state.selected_project, "project_survey", converted_data, question_set_name)
                if result["success"]:
                    st.success("✅ Page saved successfully!")
                else:
                    st.error(f"❌ Save failed: {result['message']}")
        
        # Navigation buttons
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            if current_page > 0:
                if st.button("⬅️ Previous", use_container_width=True):
                    st.session_state.strategic_survey_data.update(survey.data)
                    st.session_state.current_strategic_page -= 1
                    st.rerun()
        
        with col3:
            if current_page < total_pages - 1:
                if st.button("Next ➡️", use_container_width=True, type="primary"):
                    # Validate required questions for current page
                    missing = missing_required(page_config.get("questions", {}), survey.data)
                    if missing:
                        st.error(missing_message(missing, "proceeding"))
                    else:
                        st.session_state.strategic_survey_data.update(survey.data)
                        st.session_state.current_strategic_page += 1
                        st.rerun()
            else:
                if st.button("🎯 Complete Discovery & Generate Insights", use_container_width=True, type="primary"):
                    missing = missing_required(page_config.get("questions", {}), survey.data)
                    if missing:
                        st.error(missing_message(missing, "completing the survey"))
                    else:
                        st.session_state.strategic_survey_data.update(survey.data)
                        st.session_state.strategic_survey_completed = True
                        # Auto-save on completion
                        converted_data = convert_survey_data_keys(survey.data, st.session_state.selected_project)
                        # Get question set for this project
                        project_data = get_project_data(st.session_state.selected_project)
                        question_set_name = project_data.get('question_set') if project_data else None
                        result = save_project_data(st.session_state.selected_project, "project_survey", converted_data, question_set_name)
                        if result["success"]:
                            st.success("✅ Strategic discovery completed and saved!")
                            st.session_state.current_page = "campaign_insights"
                            st.rerun()
                        else:
                            st.warning("✅ Survey completed but save failed. Please use the Save button.")

def show_insights_page():
    """Display strategic insights and campaign opportunities"""
    # Check if strategic survey data exists (either from current session or loaded project)
    if not hasattr(st.session_state, 'strategic_survey_data') or not st.session_state.strategic_survey_data:
        st.warning("⚠️ Please complete the strategic survey first!")
        if st.button("📋 Go to Campaign Survey", use_container_width=True):
            st.session_state.current_page = "strategic_survey"
            st.session_state.current_strategic_page = 0
            st.rerun()
        return
    
    # Check for existing brainstorm_ideas and display if found
#    if hasattr(st.session_state, 'brainstorm_ideas') and st.session_state.brainstorm_ideas:
#        st.markdown('<div class="section-header">📝 Generated Content Results</div>', unsafe_allow_html=True)
#        result = st.session_state.brainstorm_ideas
#        
#        if isinstance(result, dict) and 'generated_content' in result:
#            for i, content in enumerate(result['generated_content']):
#                with st.expander(f"📄 {content.get('title', f'Content {i+1}')}", expanded=False):
#                    st.markdown(f"**Content Type:** {content.get('content_type', 'N/A')}")
#                    st.markdown(f"**Platform:** {content.get('platform', 'N/A')}")
#                    st.markdown(f"**Goal:** {content.get('goal', 'N/A')}")
#                    st.markdown("**Generated Content:**")
#                    st.markdown(content.get('content', 'No content generated'))
#        
#        # Clear results button
#        if st.button("🗑️ Clear Generated Content"):
#            if hasattr(st.session_state, 'brainstorm_ideas'):
#                del st.session_state.brainstorm_ideas
#            st.rerun()
#        
#        st.markdown("---")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<div class="section-header">🎯 Project Survey</div>', unsafe_allow_html=True)
    with col2:
        if st.button("✏️ Edit Project Survey", use_container_width=True):
            st.session_state.current_page = "strategic_survey"
            st.session_state.current_strategic_page = 0
            st.rerun()
    
    # Generate insights if not already done
    if not st.session_state.strategic_insights:
        st.info("🔍 Analyzing your responses to uncover strategic campaign opportunities...")
        st.session_state.strategic_insights = generate_strategic_insights(st.session_state.strategic_survey_data)
    
    # Generate tabs dynamically from YAML categories
    survey_pages = get_strategic_survey_pages()
    tab_labels = [f"{page['emoji']} {page['title'].split(' ', 1)[1]}" for page in survey_pages]
    tabs = st.tabs(tab_labels)
    
    for i, (tab, page) in enumerate(zip(tabs, survey_pages)):
        with tab:
            st.subheader(page['title'])
            display_insights_section(
                st.session_state.strategic_insights.get(page['category'], []),
                st.session_state.strategic_survey_data,
                page['category']
            )
    
    # Strategic AI Brainstorm Button
    st.markdown("---")

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write("Send your strategic insights to the AI brainstorm engine for campaign development recommendations.")
    
    with col2:
        if st.button("🚀 Generate Strategic Campaigns", type="primary", use_container_width=True):
            st.session_state.strategic_llm_loading = True
            st.rerun()
    
    # Handle Strategic LLM submission
    if st.session_state.strategic_llm_loading:
        with st.spinner("🤖 Analyzing strategic insights for campaign opportunities..."):
            business_data = get_business_survey_data()
            llm_result = send_to_brainstorm_llm(st.session_state.strategic_survey_data, business_data)

            st.session_state.brainstorming_data = llm_result
            st.session_state.strategic_llm_loading = False

            # The backend has already written the new ideas to
            # project_brainstorm_ideas, so surface them in the sidebar straight
            # away instead of waiting for a manual refresh.
            if llm_result.get("success") and st.session_state.get("selected_project"):
                invalidate_sidebar_ideas(st.session_state.selected_project, expand=True)
                # Keep the restore-from-DB branch below from re-fetching over
                # the fresh in-memory result.
                st.session_state.last_checked_project = st.session_state.selected_project

            st.rerun()
    
    # Check if project has changed and load existing brainstorm ideas if available
    if (hasattr(st.session_state, 'selected_project') and st.session_state.selected_project and
        (not hasattr(st.session_state, 'brainstorming_data') or not st.session_state.brainstorming_data) and
        (not hasattr(st.session_state, 'last_checked_project') or
         st.session_state.last_checked_project != st.session_state.selected_project)):

        project_ideas = get_project_brainstorming_ideas(st.session_state.selected_project)
        st.session_state.brainstorming_data = {
        "success": True,
        "data": {"brainstorm_ideas": project_ideas},
        "message": "Restored from database"
    }
        
        # Mark that we've checked this project
        st.session_state.last_checked_project = st.session_state.selected_project
    
    # Display Strategic LLM response
    if st.session_state.brainstorming_data:
        st.markdown("---")
        st.markdown('<div class="section-header">🎯 Project Post Ideas</div>', unsafe_allow_html=True)
        
        if st.session_state.brainstorming_data["success"]:
            st.success(st.session_state.brainstorming_data["message"])
            
            # Display the strategic LLM response data
            llm_data = st.session_state.brainstorming_data.get("data", {})
            if llm_data:               
                # Check if this is brainstorm ideas response
                if isinstance(llm_data, dict) and 'brainstorm_ideas' in llm_data:
                    display_brainstorm_ideas_table(llm_data)
                else:
                    # Fallback to old display format for other response types
                    if isinstance(llm_data, dict):
                        for key, value in llm_data.items():
                            st.subheader(key.replace('_', ' ').title())
                            if isinstance(value, list):
                                for item in value:
                                    st.write(f"• {item}")
                            else:
                                st.write(value)
                    else:
                        st.write(llm_data)
            else:
                st.info("Strategic AI brainstorm completed but no structured data was returned.")
        else:
            st.error(f"❌ {st.session_state.brainstorming_data['message']}")
            st.error(f"Details: {st.session_state.brainstorming_data.get('error', 'Unknown error')}")
        
        # Clear strategic response button
        if st.button("🗑️ Clear Strategic Response"):
            # Get the IDs of brainstorming ideas to delete
            brainstorm_ids_to_delete = set()
            if st.session_state.brainstorming_data and 'data' in st.session_state.brainstorming_data:
                llm_data = st.session_state.brainstorming_data['data']
                if isinstance(llm_data, dict) and 'brainstorm_ideas' in llm_data:
                    for idea in llm_data['brainstorm_ideas']:
                        if 'id' in idea:
                            brainstorm_ids_to_delete.add(idea['id'])

            # Delete only brainstorming items from items table
            if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project and brainstorm_ids_to_delete:
                try:
                    # Get current items
                    get_response = requests.get(
                        f"{LOCOL_API_URL}/api/get-items/{st.session_state.selected_project}",
                        headers=get_api_headers(),
                        timeout=10
                    )

                    if get_response.status_code == 200:
                        current_items = get_response.json()

                        # Filter out brainstorming items
                        filtered_items = [
                            item for item in current_items
                            if item.get('id') not in brainstorm_ids_to_delete
                        ]

                        # Persist the filtered list back
                        payload = {"dropdownList": filtered_items}
                        response = requests.post(
                            f"{LOCOL_API_URL}/api/persist-items/?parent={st.session_state.selected_project}",
                            json=payload,
                            headers=get_api_headers(),
                            timeout=10
                        )

                        if response.status_code == 200:
                            deleted_count = len(current_items) - len(filtered_items)
                            st.success(f"✅ {deleted_count} brainstorming item(s) cleared from database")
                        else:
                            st.warning(f"⚠️ Failed to clear items from database: HTTP {response.status_code}")
                    else:
                        st.warning(f"⚠️ Failed to get current items: HTTP {get_response.status_code}")
                except Exception as e:
                    st.warning(f"⚠️ Error clearing items from database: {str(e)}")

            # Clear the ideas themselves. Posting an empty list is a
            # clear-by-project: the endpoint deletes every row for the project
            # before re-inserting. This runs regardless of whether there were
            # ids in session state, so a project whose in-memory data is already
            # empty still gets its stored rows removed.
            if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
                clear_result = save_brainstorming_ideas_to_db(
                    st.session_state.selected_project,
                    {"brainstorm_ideas": []}
                )
                if clear_result["success"]:
                    st.success("✅ Strategic response cleared from database")
                else:
                    st.warning(f"⚠️ Failed to clear strategic response: {clear_result['message']}")

                # Drop the sidebar's cached idea list so its 💡 entries go away.
                invalidate_sidebar_ideas(st.session_state.selected_project)

            # Clear from session state
            st.session_state.brainstorming_data = None
            st.session_state.selected_ideas = set()
            st.session_state.pop("manual_edit_idea_id", None)
            st.rerun()

def display_insights_section(insights, survey_data, category):
    """Display insights for a specific section using dynamic questions"""
    questions_config = st.session_state.questions_config
    category_questions = questions_config.get(category, {})
    
    for field_key, question_info in category_questions.items():
        field_data = survey_data.get(field_key, {})
        value = field_data.get('value', '').strip()
        
        if value:
            question_text = question_info.get('question', field_key)
            
            with st.expander(f"💡 {question_text}", expanded=False):
                st.write(f"**Your Response:** {value}")
                
                # Generate campaign angle suggestions
                campaign_angles = generate_campaign_angles(field_key, value, question_text)
                if campaign_angles:
                    st.write("**Potential Campaign Angles:**")
                    for angle in campaign_angles:
                        st.write(f"• {angle}")



def generate_campaign_angles(field_key, response, question_text=""):
    """Generate specific campaign angles based on the field and response"""
    angles = []
    response_preview = response[:30] + "..." if len(response) > 30 else response
    
    # Get category from questions config
    category = get_category_from_config(field_key, st.session_state.questions_config)
    
    if "problem" in question_text.lower() or category == "emotional_motivation":
        angles = [
            f"Origin story campaign: 'Before {response_preview} existed'",
            f"Founder's journey: The problem that changed everything",
            f"Problem-solving series showcasing real solutions"
        ]
    elif "story" in question_text.lower():
        angles = [
            "Customer spotlight series with emotional testimonials",
            "Before/after transformation stories",
            "User-generated content campaigns featuring real impact"
        ]
    elif "competitor" in question_text.lower() or "unique" in question_text.lower():
        angles = [
            f"'The thing nobody talks about' campaign featuring {response_preview}",
            "Competitor comparison series highlighting unique advantages",
            "Behind-the-scenes content showing unique processes"
        ]
    elif "assumption" in question_text.lower() or "wrong" in question_text.lower():
        angles = [
            f"Myth-busting campaign: 'You think... but actually {response_preview}'",
            "Educational series correcting industry misconceptions",
            "Assumption vs. reality content series"
        ]
    elif "customer" in question_text.lower() and ("buy" in question_text.lower() or "unexpected" in question_text.lower()):
        angles = [
            f"Spotlight unexpected user segments: {response_preview}",
            "Case studies from surprising industries",
            "Expansion targeting campaigns for new segments"
        ]
    elif "stress" in question_text.lower() or "happening" in question_text.lower():
        angles = [
            f"Timely relief campaign addressing {response_preview}",
            "Stress-solution matching content series",
            "Current events tie-in campaigns"
        ]
    elif "secret" in question_text.lower() or category == "differentiators":
        angles = [
            f"Behind-the-scenes reveal: {response_preview}",
            "Competitive advantage series",
            "Process transparency campaigns"
        ]
    else:
        # Generic angles based on category
        if category == "emotional_motivation":
            angles = ["Emotional storytelling campaign", "Impact-focused content series", "Customer transformation stories"]
        elif category == "positioning_angles":
            angles = ["Unique positioning campaign", "Differentiation content series", "Educational myth-busting content"]
        elif category == "audience_insights":
            angles = ["Audience spotlight campaign", "Customer behavior insights series", "Expansion opportunity content"]
        elif category == "cultural_timing":
            angles = ["Timely relevance campaign", "Trend-leveraging content series", "Urgency-driven messaging"]
        else:
            angles = ["Develop this insight into a content series", "Use as unique selling proposition", "Create educational content around this angle"]
    
    return angles[:3]  # Return top 3 suggestions




def display_brainstorm_ideas_table(brainstorm_data):
    """Display brainstorm ideas as an editable table with selection"""
    if 'brainstorm_ideas' not in brainstorm_data:
        st.error("No brainstorm ideas found in response")
        return
    
    ideas = brainstorm_data['brainstorm_ideas']

    # Jump straight to a specific idea's location in the list (set by the global sidebar nav)
    navigate_to_idea = st.session_state.pop("navigate_to_idea", None)
    if navigate_to_idea:
        st.session_state["scroll_to_idea_id"] = navigate_to_idea

    with st.expander("➕ Add Campaign Idea Manually", expanded=False):
        with st.form("add_idea_form", clear_on_submit=True):
            new_title = st.text_input("Title")
            new_description = st.text_area("Description", height=120)
            col1, col2 = st.columns(2)
            with col1:
                new_content_type = st.selectbox("Content Type", options=CONTENT_TYPE_OPTIONS)
            with col2:
                new_platform = st.text_input("Platform", value="Reddit")
            new_goal = st.text_area("Goal", height=80)
            if st.form_submit_button("➕ Add Idea", type="primary"):
                if new_title.strip():
                    add_idea_to_brainstorm_data({
                        'id': str(uuid7()),
                        'title': new_title,
                        'description': new_description,
                        'content_type': new_content_type,
                        'platform': new_platform,
                        'goal': new_goal
                    })
                    st.success("Idea added")
                    st.rerun()
                else:
                    st.error("Title is required")

    if not ideas:
        st.info("No brainstorm ideas generated")
        return

    # Initialize session state for selected ideas if not exists
    if 'selected_ideas' not in st.session_state:
        st.session_state.selected_ideas = set()
    
    # Check if any modal is currently open
    any_modal_open = any(st.session_state.get(f"edit_modal_{idea.get('id', f'idea_{i}')}", False) for i, idea in enumerate(ideas))
    
    # If a modal is open, show only the modal
    if any_modal_open:
        for i, idea in enumerate(ideas):
            idea_id = idea.get('id', f'idea_{i}')
            if st.session_state.get(f"edit_modal_{idea_id}", False):
                st.markdown(f'<div id="idea-modal-anchor-{idea_id}"></div>', unsafe_allow_html=True)
                edit_idea_modal(idea, idea_id, i)
                if st.session_state.pop("scroll_to_modal", False):
                    # Streamlit scrolls its own inner content container (data-testid="stMain"),
                    # not the browser window - compute the anchor's offset relative to it and
                    # scroll that directly, rather than relying on scrollIntoView() to find it.
                    # The nonce guards against the same idea being jumped to twice in a row,
                    # which would otherwise make this script's content byte-identical to the
                    # last render and get skipped by the browser (no reload => no re-execution).
                    components.html(f"""
                        <script>
                            // nonce: {time.time()}
                            setTimeout(function() {{
                                try {{
                                    const mainEl = window.parent.document.querySelector('[data-testid="stMain"]');
                                    const el = window.parent.document.getElementById("idea-modal-anchor-{idea_id}");
                                    console.log("[scroll_to_modal] stMain found?", mainEl, "el found?", el);
                                    if (el && mainEl) {{
                                        const targetTop = el.getBoundingClientRect().top - mainEl.getBoundingClientRect().top + mainEl.scrollTop;
                                        mainEl.scrollTo({{top: targetTop, behavior: "smooth"}});
                                    }} else if (el) {{
                                        el.scrollIntoView({{behavior: "smooth", block: "start"}});
                                    }}
                                    console.log("[scroll_to_modal] scroll called OK");
                                }} catch (e) {{
                                    console.error("[scroll_to_modal] error:", e);
                                }}
                            }}, 100);
                        </script>
                    """, height=1)
                break
        return  # Exit early, don't show the idea list

    # Display each idea as an expandable card with checkbox and edit controls
    for i, idea in enumerate(ideas):
        idea_id = idea.get('id', f'idea_{i}')
        st.markdown(f'<div id="idea-{idea_id}"></div>', unsafe_allow_html=True)
        title = idea.get('title', f'Idea {i+1}')

        # Check if this idea has generated content for Content Editor button
        has_generated_content = ('generated_content' in idea and 
                                idea.get('generated_content') and 
                                str(idea.get('generated_content')).strip() != "")
        
        # Create header with title on left, buttons in middle, checkbox on right
        # Adjust columns based on whether Content Editor button should be shown
        if has_generated_content:
            col1, col2, col3, col4 = st.columns([0.5, 0.15, 0.15, 0.2])
        else:
            col1, col2, col3 = st.columns([0.6, 0.2, 0.2])
        
        with col1:
            st.markdown(f"**{title}**")
        
        with col2:
            if st.button("✏️ Edit", key=f"edit_{idea_id}", help="Edit this idea", use_container_width=True):
                # Close all other modals first
                for j, other_idea in enumerate(ideas):
                    other_idea_id = other_idea.get('id', f'idea_{j}')
                    if other_idea_id != idea_id:
                        st.session_state[f"edit_modal_{other_idea_id}"] = False
                # Open this modal
                st.session_state[f"edit_modal_{idea_id}"] = True
                st.session_state["manual_edit_idea_id"] = idea_id
                st.rerun()
        
        # Content Editor button (only show if there's generated content)
        if has_generated_content:
            with col3:
                project_id = st.session_state.get('selected_project', '')
                jwt_token = st.session_state.get('jwt_token', '')
                # The token rides in the URL *fragment*, not the query string:
                # browsers never transmit a fragment, so it stays out of the
                # ingress access log and out of the Referer header. That matters
                # because Web and BackEnd sit on one host behind the ingress
                # (k8s/05-ingress.yaml), making the editor same-origin with the
                # API - a query-string token would be logged on every request.
                # The editor strips it from the URL as soon as it reads it.
                content_editor_url = f"{LOCOL_WWW_URL}/www/index.html?project_id={project_id}&item_id={idea_id}#jwt={jwt_token}"
                
                # Use st.link_button for reliable new tab opening
                st.link_button(
                    "📝 Content Editor", 
                    url=content_editor_url,
                    help="Open in Content Editor",
                    use_container_width=True
                )
            
            # Checkbox column
            with col4:
                pass  # Will be filled with checkbox code below
        else:
            # Checkbox column (when no Content Editor button)
            with col3:
                pass  # Will be filled with checkbox code below
        
        # Set the appropriate column for checkbox
        checkbox_col = col4 if has_generated_content else col3
        with checkbox_col:
            is_selected = st.checkbox(
                "Generate Content",
                key=f"select_{idea_id}",
                value=idea_id in st.session_state.selected_ideas
            )
            
            # Update session state based on checkbox
            if is_selected and idea_id not in st.session_state.selected_ideas:
                st.session_state.selected_ideas.add(idea_id)
            elif not is_selected and idea_id in st.session_state.selected_ideas:
                st.session_state.selected_ideas.remove(idea_id)
        
        with st.expander("View Details", expanded=True):
            st.markdown(f"**Description:**")
            st.write(idea.get('description', 'No description'))
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Content Type:** {idea.get('content_type', 'N/A')}")
                st.markdown(f"**Platform:** {idea.get('platform', 'N/A')}")
            
            with col_b:
                st.markdown(f"**Goal:**")
                st.write(idea.get('goal', 'No goal specified'))
            
            # Show generated content if it exists
            if has_generated_content:
                st.markdown("---")
                st.markdown("### 🤖 Generated Content")
                # generated_content is HTML from the LLM - sanitize rather than escape,
                # so it renders formatted without trusting raw model output.
                st.markdown(sanitize_generated_html(idea.get('generated_content')), unsafe_allow_html=True)
                
                if 'prompt_template_used' in idea:
                    st.caption(f"Template used: {idea['prompt_template_used']}")
                    
                if 'timestamp' in idea:
                    st.caption(f"Generated: {idea['timestamp']}")
            elif 'generation_error' in idea:
                st.markdown("---")
                st.error(f"⚠️ Generation Error: {idea['generation_error']}")
        
        # Add a visual separator
        st.markdown("---")

    scroll_to_idea_id = st.session_state.pop("scroll_to_idea_id", None)
    if scroll_to_idea_id:
        # Same offset-computation pattern as the modal's scroll_to_modal script above -
        # scrolls stMain directly rather than relying on scrollIntoView() to find it.
        components.html(f"""
            <script>
                // nonce: {time.time()}
                setTimeout(function() {{
                    try {{
                        const mainEl = window.parent.document.querySelector('[data-testid="stMain"]');
                        const el = window.parent.document.getElementById("idea-{scroll_to_idea_id}");
                        if (el && mainEl) {{
                            const targetTop = Math.max(0, el.getBoundingClientRect().top - mainEl.getBoundingClientRect().top + mainEl.scrollTop - 70);
                            mainEl.scrollTo({{top: targetTop, behavior: "smooth"}});
                        }} else if (el) {{
                            el.scrollIntoView({{behavior: "smooth", block: "start"}});
                        }}
                    }} catch (e) {{ console.error("[scroll_to_idea] error:", e); }}
                }}, 100);
            </script>
        """, height=1)

    # Display selection summary and generate content button
    st.markdown("---")
    st.markdown("### 🚀 Content Generation")
    
    # Show selection summary
    if st.session_state.selected_ideas:
        st.success(f"✅ {len(st.session_state.selected_ideas)} idea(s) selected for content generation")
    else:
        st.info("Select ideas above using the checkboxes to generate content")
    
    # Voice the drafts are written in. Persisted against the project, so it holds
    # across reloads and matches the picker inside each idea's brainstorm panel.
    project_id_for_voice = st.session_state.get('selected_project')
    if project_id_for_voice:
        voice_selectbox(project_id_for_voice, key=f"generate_voice_{project_id_for_voice}")

    # Generate content button
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("🔄 Refresh Content", use_container_width=True):
            project_id = st.session_state.get('selected_project')
            if project_id:
                fresh_ideas = get_project_brainstorming_ideas(project_id)
                fresh_by_id = {fi.get('id'): fi for fi in fresh_ideas}
                if (st.session_state.brainstorming_data and
                    'data' in st.session_state.brainstorming_data and
                    'brainstorm_ideas' in st.session_state.brainstorming_data['data']):
                    for i, existing_idea in enumerate(st.session_state.brainstorming_data['data']['brainstorm_ideas']):
                        fresh_idea = fresh_by_id.get(existing_idea.get('id'))
                        if fresh_idea:
                            st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['generated_content'] = fresh_idea.get('generated_content', '')
                            st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['prompt_template_used'] = fresh_idea.get('prompt_template_used', '')
                            st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['timestamp'] = fresh_idea.get('timestamp', '')
                            if 'generation_error' in fresh_idea:
                                st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['generation_error'] = fresh_idea['generation_error']
                            else:
                                st.session_state.brainstorming_data['data']['brainstorm_ideas'][i].pop('generation_error', None)
                st.success("✅ Refreshed content from the database")
                st.rerun()
            else:
                st.warning("No project selected")

    with col2:
        if st.button("🚀 Generate Content", 
                    type="primary", 
                    disabled=len(st.session_state.selected_ideas) == 0,
                    use_container_width=True):
            # Create DataFrame with selection state for compatibility
            df_data = []
            for i, idea in enumerate(ideas):
                idea_id = idea.get('id', f'idea_{i}')
                df_data.append({
                    'Select': idea_id in st.session_state.selected_ideas,
                    'ID': idea_id,
                    'Title': idea.get('title', ''),
                    'Description': idea.get('description', ''),
                    'Content Type': idea.get('content_type', ''),
                    'Platform': idea.get('platform', ''),
                    'Goal': idea.get('goal', '')
                })
            
            df_with_selections = pd.DataFrame(df_data)
            generate_content_for_selected_ideas(df_with_selections)
    
    with col3:
        if st.button("🗑️ Clear Selection", use_container_width=True):
            if 'selected_ideas' in st.session_state:
                st.session_state.selected_ideas.clear()
            st.rerun()

def edit_idea_modal(idea, idea_id, index):
    """Display edit modal for an idea"""
    st.markdown("### ✏️ Edit Idea")
    
    # Create form for editing
    with st.form(f"edit_form_{idea_id}"):
        st.markdown(f"**Editing Idea #{index + 1}**")
        
        # Edit fields
        new_title = st.text_input("Title", value=idea.get('title', ''), key=f"edit_title_{idea_id}")
        new_description = st.text_area("Description", value=idea.get('description', ''), height=120, key=f"edit_desc_{idea_id}")
        
        col1, col2 = st.columns(2)
        with col1:
            new_content_type = st.selectbox(
                "Content Type",
                options=CONTENT_TYPE_OPTIONS,
                index=CONTENT_TYPE_OPTIONS.index(idea.get('content_type', 'Blog Post')) if idea.get('content_type') in CONTENT_TYPE_OPTIONS else 0,
                key=f"edit_content_type_{idea_id}"
            )
        
        with col2:
            new_platform = st.text_input("Platform", value=idea.get('platform', ''), key=f"edit_platform_{idea_id}")
        
        new_goal = st.text_area("Goal", value=idea.get('goal', ''), height=80, key=f"edit_goal_{idea_id}")
        
        # Form buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.form_submit_button("💾 Save Changes", type="primary"):
                # Update the idea in the session state
                update_idea_in_brainstorm_data(idea_id, {
                    'title': new_title,
                    'description': new_description,
                    'content_type': new_content_type,
                    'platform': new_platform,
                    'goal': new_goal
                })
                st.session_state[f"edit_modal_{idea_id}"] = False
                st.session_state.pop("manual_edit_idea_id", None)
                st.success("✅ Idea updated successfully!")
                st.rerun()

        with col2:
            if st.form_submit_button("❌ Cancel"):
                st.session_state[f"edit_modal_{idea_id}"] = False
                st.session_state.pop("manual_edit_idea_id", None)
                st.rerun()

        with col3:
            if st.form_submit_button("🗑️ Delete", help="Delete this idea"):
                delete_idea_from_brainstorm_data(idea_id)
                st.session_state[f"edit_modal_{idea_id}"] = False
                st.session_state.pop("manual_edit_idea_id", None)
                st.success("🗑️ Idea deleted successfully!")
                st.rerun()

    # --- Brainstorm Content Snippet section (outside the form) ---
    st.markdown("---")
    st.markdown("#### 💡 Brainstorm Content Snippet")

    # Load existing content snippets on first render
    if f"brainstorm_content_snippets_{idea_id}" not in st.session_state:
        try:
            sub_resp = requests.get(
                f"{LOCOL_API_URL}/api/brainstorm-content-snippets",
                params={"idea_id": idea_id},
                headers=get_api_headers(),
                timeout=10,
            )
            snippets = sub_resp.json() if sub_resp.status_code == 200 else []
        except Exception:
            snippets = []
        st.session_state[f"brainstorm_content_snippets_{idea_id}"] = snippets
        # Pre-populate with the latest snippet on first open
        if snippets:
            st.session_state[f"brainstorm_prompt_{idea_id}"] = snippets[0]["prompt"]
            st.session_state[f"brainstorm_response_{idea_id}"] = snippets[0]["response"]
            st.session_state[f"brainstorm_last_applied_row_{idea_id}"] = 0

    # Apply a pending row selection before widgets render
    apply_key = f"brainstorm_apply_{idea_id}"
    if apply_key in st.session_state:
        row_data = st.session_state.pop(apply_key)
        st.session_state[f"brainstorm_prompt_{idea_id}"] = row_data["prompt"]
        st.session_state[f"brainstorm_response_{idea_id}"] = row_data["response"]

    brainstorm_prompt = st.text_input(
        "Brainstorming Prompt",
        placeholder="e.g. Suggest 5 headline variations for this campaign idea",
        key=f"brainstorm_prompt_{idea_id}"
    )

    # Same project-level selection as the Generate Content picker - choosing here
    # changes it there too, and vice versa.
    brainstorm_project_id = st.session_state.get('selected_project')
    brainstorm_voice_id = None
    if brainstorm_project_id:
        brainstorm_voice_id = voice_selectbox(
            brainstorm_project_id,
            key=f"brainstorm_voice_{idea_id}",
            help_text="Brainstorming output is written in this saved writing style.",
        )

    if st.button("🧠 Brainstorm Content Snippet", key=f"brainstorm_btn_{idea_id}"):
        if not brainstorm_prompt.strip():
            st.warning("Please enter a brainstorming prompt.")
        else:
            with st.spinner("Brainstorming..."):
                try:
                    response = requests.post(
                        f"{LOCOL_API_URL}/api/brainstorm-idea",
                        json={
                            "idea_id": idea_id,
                            "prompt": brainstorm_prompt.strip(),
                            "title": idea.get("title", ""),
                            "description": idea.get("description", ""),
                            "content_type": idea.get("content_type", ""),
                            "platform": idea.get("platform", ""),
                            "goal": idea.get("goal", ""),
                            "voice_id": brainstorm_voice_id,
                        },
                        headers=get_api_headers(),
                        timeout=LLM_REQUEST_TIMEOUT,
                    )
                    if response.status_code == 200:
                        st.session_state[f"brainstorm_response_{idea_id}"] = response.json().get("response", "")
                        # Reload content snippets grid
                        sub_resp = requests.get(
                            f"{LOCOL_API_URL}/api/brainstorm-content-snippets",
                            params={"idea_id": idea_id},
                            headers=get_api_headers(),
                            timeout=10,
                        )
                        if sub_resp.status_code == 200:
                            st.session_state[f"brainstorm_content_snippets_{idea_id}"] = sub_resp.json()
                    else:
                        st.error(f"Error {response.status_code}: {response.text}")
                except requests.exceptions.Timeout:
                    st.error("Request timed out. Please try again.")
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")

    if st.session_state.get(f"brainstorm_response_{idea_id}"):
        st.text_area(
            "Brainstorming Response",
            value=st.session_state[f"brainstorm_response_{idea_id}"],
            height=300,
            key=f"brainstorm_result_{idea_id}"
        )

    content_snippets = st.session_state.get(f"brainstorm_content_snippets_{idea_id}", [])
    if content_snippets:
        st.markdown("##### Previous Content Snippets")
        import pandas as pd
        df = pd.DataFrame(content_snippets)
        df = df.rename(columns={"create_datetime": "Datetime", "prompt": "Prompt", "response": "Content Snippet"})
        selection = st.dataframe(
            df[["Datetime", "Prompt", "Content Snippet"]],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"brainstorm_snippets_grid_{idea_id}"
        )
        if selection.selection.rows:
            row_idx = selection.selection.rows[0]
            last_key = f"brainstorm_last_applied_row_{idea_id}"
            if st.session_state.get(last_key) != row_idx:
                st.session_state[last_key] = row_idx
                st.session_state[f"brainstorm_apply_{idea_id}"] = {
                    "prompt": content_snippets[row_idx]["prompt"],
                    "response": content_snippets[row_idx]["response"],
                }
                st.rerun()

def add_idea_to_brainstorm_data(new_idea):
    """Add a manually-created idea to the brainstorm data"""
    if (st.session_state.brainstorming_data and
        'data' in st.session_state.brainstorming_data and
        'brainstorm_ideas' in st.session_state.brainstorming_data['data']):

        st.session_state.brainstorming_data['data']['brainstorm_ideas'].append(new_idea)

        # Save to database if project is selected
        if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
            save_brainstorming_ideas_to_db(st.session_state.selected_project, st.session_state.brainstorming_data['data'])

def update_idea_in_brainstorm_data(idea_id, updated_fields):
    """Update an idea in the brainstorm data"""
    if (st.session_state.brainstorming_data and 
        'data' in st.session_state.brainstorming_data and 
        'brainstorm_ideas' in st.session_state.brainstorming_data['data']):
        
        for i, idea in enumerate(st.session_state.brainstorming_data['data']['brainstorm_ideas']):
            if idea.get('id') == idea_id:
                # Update the idea with new values
                st.session_state.brainstorming_data['data']['brainstorm_ideas'][i].update(updated_fields)
                
                # Save to database if project is selected
                if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
                    save_brainstorming_ideas_to_db(st.session_state.selected_project, st.session_state.brainstorming_data['data'])
                break

def delete_idea_from_brainstorm_data(idea_id):
    """Delete an idea from the brainstorm data"""
    if (st.session_state.brainstorming_data and 
        'data' in st.session_state.brainstorming_data and 
        'brainstorm_ideas' in st.session_state.brainstorming_data['data']):
        
        st.session_state.brainstorming_data['data']['brainstorm_ideas'] = [
            idea for idea in st.session_state.brainstorming_data['data']['brainstorm_ideas']
            if idea.get('id') != idea_id
        ]
        
        # Remove from selected ideas if it was selected
        if idea_id in st.session_state.selected_ideas:
            st.session_state.selected_ideas.remove(idea_id)
        
        # Save to database if project is selected
        if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
            save_brainstorming_ideas_to_db(st.session_state.selected_project, st.session_state.brainstorming_data['data'])


def generate_content_for_selected_ideas(df):
    """Generate content for selected brainstorm ideas"""
    selected_ideas = df[df['Select'] == True]
    
    if len(selected_ideas) == 0:
        st.warning("Please select at least one idea to generate content for")
        return

    # The backend runs one LLM call per idea and rejects an over-long batch with a
    # 422; say so here rather than letting that surface as a raw HTTP error.
    if len(selected_ideas) > MAX_IDEAS_PER_BATCH:
        st.warning(
            f"You've selected {len(selected_ideas)} ideas. Content is generated one "
            f"idea at a time, so batches are limited to {MAX_IDEAS_PER_BATCH} — "
            f"please deselect {len(selected_ideas) - MAX_IDEAS_PER_BATCH} and run the "
            f"rest afterwards."
        )
        return


    # Convert selected ideas back to the format expected by the API
    ideas_for_generation = []
    for _, row in selected_ideas.iterrows():
        ideas_for_generation.append({
            'id': row['ID'],
            'title': row['Title'],
            'description': row['Description'], 
            'content_type': row['Content Type'],
            'platform': row['Platform'],
            'goal': row['Goal']
        })
    
    # Call the generate-project-items API
    try:
        # Get business survey data
        business_data = get_business_survey_data()
        
        # Extract only value fields from business survey data
        business_survey_values = {}
        if business_data:
            for key, field_data in business_data.items():
                if isinstance(field_data, dict) and 'value' in field_data:
                    business_survey_values[key] = field_data['value']
                else:
                    business_survey_values[key] = field_data
        
        # Voice chosen in the picker above; None means the neutral house style.
        voice_id = st.session_state.get(f"project_voice_{st.session_state.selected_project}")

        payload = {
            "project_id": st.session_state.selected_project,
            "business_survey": business_survey_values,
            "strategic_survey": st.session_state.strategic_survey_data,
            "selected_ideas": ideas_for_generation,
            "voice_id": voice_id,
            "timestamp": datetime.now().isoformat()
        }

        voice_note = ""
        if voice_id:
            voice_name = next(
                (v["name"] for v in st.session_state.get("voices_cache", []) if v["id"] == voice_id),
                None
            )
            if voice_name:
                voice_note = f" in the voice of {voice_name}"

        with st.spinner(f"🤖 Generating content for {len(ideas_for_generation)} selected idea(s){voice_note}..."):
            response = requests.post(
                f"{LOCOL_API_URL}/api/generate-project-items",
                json=payload,
                headers=get_api_headers(),
                timeout=LLM_REQUEST_TIMEOUT
            )
        
        if response.status_code == 200:
            result = response.json()
            st.success(f"✅ Successfully generated content for {len(ideas_for_generation)} idea(s)!")
            
            # Update brainstorm data with generated content
            if isinstance(result, dict) and 'data' in result and 'items_dict' in result['data']:
                items_dict = result['data']['items_dict']
                
                # Update the brainstorming_data with generated content
                if (st.session_state.brainstorming_data and 
                    'data' in st.session_state.brainstorming_data and 
                    'brainstorm_ideas' in st.session_state.brainstorming_data['data']):
                    
                    for i, idea in enumerate(st.session_state.brainstorming_data['data']['brainstorm_ideas']):
                        idea_id = idea.get('id')
                        if idea_id in items_dict:
                            item_data = items_dict[idea_id]
                            # Add generated content to the idea
                            st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['generated_content'] = item_data.get('generated_content', '')
                            st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['prompt_template_used'] = item_data.get('prompt_template_used', '')
                            st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['timestamp'] = item_data.get('timestamp', '')
                            
                            # Handle generation errors
                            if 'generation_error' in item_data:
                                st.session_state.brainstorming_data['data']['brainstorm_ideas'][i]['generation_error'] = item_data['generation_error']
                # Save updated brainstorm data to database
                if hasattr(st.session_state, 'selected_project') and st.session_state.selected_project:
                    save_brainstorming_ideas_to_db(st.session_state.selected_project, st.session_state.brainstorming_data['data'])
                
                # Force a rerun to refresh the display with new content
                st.rerun()
            else:
                st.info("Content generated successfully but no structured response received")
                st.json(result)
            
        else:
            st.error(f"❌ Failed to generate content: HTTP {response.status_code}")
            st.error(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        st.error(f"❌ Could not connect to content generation server at {LOCOL_API_URL}")
    except requests.exceptions.Timeout:
        st.error(f"❌ Content generation request timed out after {LLM_TIMEOUT_DESCRIPTION}")
    except Exception as e:
        st.error(f"❌ Error generating content: {str(e)}")


if __name__ == "__main__":
    main()

