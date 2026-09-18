# surveyRequired.py - shared required/optional handling for the surveys
#
# Library module, not a Streamlit page: functions and constants only, no `st.*` calls,
# so either survey can import it without side effects. See projectState.py and
# surveyPages.py for the same pattern.
#
# A question is required when its YAML definition carries `required: true`, and optional
# otherwise. The Business Survey (survey.py) and the Project Survey (projectSurvey.py)
# both render the marker and enforce the rule through here, so the two can't drift apart.

# Escaped because Streamlit renders widget labels and captions as markdown - a bare
# asterisk would open an emphasis span and vanish.
REQUIRED_MARKER = " \\*"

SOME_REQUIRED_LEGEND = "Questions marked \\* are required — everything else is optional."
NONE_REQUIRED_LEGEND = "All questions on this page are optional."


def is_required(field_def):
    """True if a question's YAML definition marks it mandatory."""
    return bool(field_def.get("required"))


def question_label(field_def):
    """The question text, with the required marker appended when it applies."""
    return field_def["question"] + (REQUIRED_MARKER if is_required(field_def) else "")


def page_legend(questions):
    """Caption for one page, telling the reader which way that page runs.

    A page with nothing required carries no markers at all, so it says so outright -
    otherwise an all-optional page is indistinguishable from one where the markers
    were forgotten.
    """
    if any(is_required(fd) for fd in questions.values()):
        return SOME_REQUIRED_LEGEND
    return NONE_REQUIRED_LEGEND


def is_blank(value):
    """True if an answer counts as unfilled.

    The "Select" test catches the placeholder first option of a selectbox
    ("Select Industry", "Select Range") - a real value as far as the widget is
    concerned, but it means the user never chose.
    """
    if not value:
        return True
    if isinstance(value, str):
        return not value.strip() or "Select" in value
    if isinstance(value, list):
        return not value
    return False


def missing_required(questions, survey_data):
    """Return the question text of each unanswered required question on a page.

    `questions` is that page's field_key -> definition mapping; `survey_data` is keyed
    by the same field keys, holding either a raw answer or a {'value': ...} dict.
    """
    missing = []
    for field_key, field_def in questions.items():
        if not is_required(field_def):
            continue
        field_data = survey_data.get(field_key, {})
        value = field_data.get('value') if isinstance(field_data, dict) else field_data
        if is_blank(value):
            missing.append(field_def["question"])
    return missing


def missing_message(missing, action):
    """Error text naming the unanswered questions.

    Joined with semicolons, not commas - the question text contains commas.
    """
    return f"Please answer these required questions before {action}: " + "; ".join(missing)
