# surveyPages.py - business survey question/page-config loaders
#
# Library module, not a Streamlit page: functions only, no `st.*` calls at
# import time, so main.py's sidebar nav can import it without pulling in
# survey.py's page-level side effects. See projectState.py for the same pattern.
import os
import yaml
import streamlit as st


def load_business_survey_questions():
    """Load business survey questions from YAML file"""
    yaml_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'question-sets', 'business_survey_questions.yaml'))
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        st.error(f"Business survey questions file not found at {yaml_path}")
        return {}
    except yaml.YAMLError as e:
        st.error(f"Error parsing business survey questions YAML: {e}")
        return {}


@st.cache_data
def load_business_survey_page_configs():
    """Load business survey page configurations from YAML file"""
    yaml_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'question-sets', 'business_survey_page_configs.yaml'))
    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        st.error(f"Business survey page configs file not found at {yaml_path}")
        return {}
    except yaml.YAMLError as e:
        st.error(f"Error parsing business survey page configs YAML: {e}")
        return {}


_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-"})


def canonicalize_option(value, options):
    """Map a stored answer onto its current option, ignoring dash style.

    Option text doubles as the stored value, so respelling "1–3 years" as
    "1-3 years" in the YAML would orphan answers saved under the old spelling.
    Match on a dash-normalized form and return the current option text.
    """
    if isinstance(value, list):
        return [canonicalize_option(v, options) for v in value]
    if not isinstance(value, str) or value in options:
        return value
    normalized = value.translate(_DASHES)
    for opt in options:
        if opt.translate(_DASHES) == normalized:
            return opt
    return value


def get_business_survey_pages():
    """Generate survey pages configuration from YAML questions and page configs"""
    questions_config = load_business_survey_questions()
    page_configs = load_business_survey_page_configs()
    pages = []
    for category_key, questions in questions_config.items():
        if category_key in ('name', 'page_configs_file'):
            continue
        if category_key in page_configs:
            cfg = page_configs[category_key]
            pages.append({
                "category": category_key,
                "title": cfg["title"],
                "description": cfg["description"],
                "emoji": cfg.get("emoji", ""),
                "questions": questions,
            })
    return pages
