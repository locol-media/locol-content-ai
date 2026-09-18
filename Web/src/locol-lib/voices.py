"""
Shared helpers for saved voices - the writing-style profiles content is generated in.

Used by the Find Your Voice page (which manages them) and by Campaign Projects
(which picks one per project), so both read the same session cache and a voice
created or deleted on one page is reflected on the other.
"""
import requests
import streamlit as st

from apiClient import LOCOL_API_URL, get_api_headers

# Label for "generate in the neutral house style". Not a voice name - the picker
# maps it back to None before anything is sent or stored.
NO_VOICE_LABEL = "— No voice —"


def fetch_voices():
    """Return every saved voice, newest first, or [] if the backend is unreachable."""
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/voices",
            headers=get_api_headers(),
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return []


def get_cached_voices():
    """Voices for this session, fetched once and reused until something changes them."""
    if "voices_cache" not in st.session_state:
        st.session_state.voices_cache = fetch_voices()
    return st.session_state.voices_cache


def name_exists(name: str, exclude_id: str = None) -> bool:
    """Return True if a voice with the given name already exists (case-insensitive)."""
    voices = st.session_state.get("voices_cache", [])
    for v in voices:
        if v["name"].strip().lower() == name.strip().lower():
            if exclude_id and v["id"] == exclude_id:
                continue
            return True
    return False


def fetch_project_voice(project_id: str):
    """Return the voice id selected for a project, or None.

    The backend joins through to the voice itself, so a selection left behind by a
    deleted voice comes back as no selection.
    """
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/projects/{project_id}/voice",
            headers=get_api_headers(),
            timeout=10,
        )
        if response.status_code == 200:
            return (response.json() or {}).get("voice_id")
    except Exception:
        pass
    return None


def save_project_voice(project_id: str, voice_id):
    """Persist (or clear, with voice_id None) the voice a project generates in."""
    try:
        response = requests.put(
            f"{LOCOL_API_URL}/api/projects/{project_id}/voice",
            json={"voice_id": voice_id},
            headers=get_api_headers(),
            timeout=10,
        )
        return response.status_code == 200 and response.json().get("success", False)
    except Exception:
        return False


def _voice_changed(project_id: str, key: str, labels: list, ids: list):
    """Persist the picker's new selection against the project.

    Runs as the selectbox's on_change callback, so the project's selection is already
    up to date when the rerun re-renders the pickers. `labels` and `ids` are the lists
    the widget was rendered with, so a voice added or removed in between can't shift
    the choice onto a different id.
    """
    choice = st.session_state.get(key)
    try:
        chosen_id = ids[labels.index(choice)]
    except ValueError:
        chosen_id = None

    state_key = f"project_voice_{project_id}"
    if chosen_id != st.session_state.get(state_key):
        st.session_state[state_key] = chosen_id
        save_project_voice(project_id, chosen_id)


def voice_selectbox(project_id: str, key: str, label: str = "🎤 Voice", help_text: str = None):
    """Render a voice picker for a project and return the selected voice id, or None.

    The selection is stored per project rather than per widget, so the picker beside
    Generate Content and the one inside an idea's brainstorm panel always agree, and
    it survives a page reload. A stored voice that no longer exists falls back to
    "no voice" instead of leaving a stale name on screen.
    """
    voices = get_cached_voices()
    state_key = f"project_voice_{project_id}"

    if state_key not in st.session_state:
        st.session_state[state_key] = fetch_project_voice(project_id)

    ids = [None] + [v["id"] for v in voices]
    labels = [NO_VOICE_LABEL] + [v["name"] for v in voices]

    selected_id = st.session_state[state_key]
    index = ids.index(selected_id) if selected_id in ids else 0

    if help_text is None:
        help_text = (
            "Drafts are written in this saved writing style. Manage voices under "
            "Settings and Tools → 🎤 Find your voice."
        )

    # A keyed widget's own stored value wins over `index` on reruns, so point it at
    # the project's selection before rendering. Without this, a second picker for the
    # same project (the one in an idea's brainstorm panel) would still be holding the
    # value it was last rendered with and would show that stale choice. The picker the
    # user just changed is already in step here, because its on_change callback ran
    # before this rerun reached `index` above.
    if st.session_state.get(key) != labels[index]:
        st.session_state[key] = labels[index]

    st.selectbox(
        label,
        options=labels,
        index=index,
        key=key,
        help=help_text,
        on_change=_voice_changed,
        args=(project_id, key, labels, ids),
    )

    return st.session_state[state_key]
