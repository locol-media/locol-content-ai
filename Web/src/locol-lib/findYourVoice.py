import requests
import streamlit as st

from apiClient import LOCOL_API_URL, LLM_REQUEST_TIMEOUT, get_api_headers, FIND_YOUR_VOICE_ENABLED
from voices import fetch_voices, name_exists


# ── Page header ──────────────────────────────────────────────────────────────

st.title("Find Your Voice")
st.write(
    "A voice is a description of how someone writes. Save one here and you can pick it "
    "on a campaign project, so every draft is written in that style instead of a generic "
    "AI tone."
)

# ── Section 1: Analyze ───────────────────────────────────────────────────────

st.subheader("🔍 Analyze a Reddit account")

if not FIND_YOUR_VOICE_ENABLED:
    st.warning(
        "**Reddit analysis is currently unavailable.** This tool worked by reading "
        "search results for a Reddit account, and Reddit now blocks the automated "
        "access it depended on. Write your voice by hand below instead — you know how "
        "you sound better than a search engine does."
    )

reddit_username = st.text_input(
    "Reddit Username",
    placeholder="e.g. spez",
    disabled=not FIND_YOUR_VOICE_ENABLED,
)

if st.button("Analyze Voice", type="primary", disabled=not FIND_YOUR_VOICE_ENABLED):
    if not reddit_username.strip():
        st.error("Please enter a Reddit username.")
    else:
        with st.spinner(f"Searching for u/{reddit_username.strip()}'s writing style..."):
            try:
                response = requests.post(
                    f"{LOCOL_API_URL}/api/findYourVoice",
                    json={"reddit_username": reddit_username.strip()},
                    headers=get_api_headers(),
                    timeout=LLM_REQUEST_TIMEOUT,
                )
                if response.status_code == 200:
                    data = response.json()
                    if "error" in data:
                        st.error(data["error"])
                    elif data.get("voice_prompt"):
                        st.session_state.voice_prompt = data["voice_prompt"]
                        st.session_state.analyzed_username = reddit_username.strip()
                        st.session_state.voice_name_input = f"{reddit_username.strip()}'s voice"
                    else:
                        st.error("The AI returned an empty response. Check the backend logs for details.")
                else:
                    st.error(f"Error {response.status_code}: {response.text}")
            except requests.exceptions.Timeout:
                st.error("The request timed out. The analysis may take a while — please try again.")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

if st.session_state.get("voice_prompt"):
    st.success("Voice analysis complete!")
    st.text_area(
        "Recommended Voice Prompt",
        value=st.session_state.voice_prompt,
        height=300,
        help="Copy this prompt and use it as a system prompt when generating content.",
    )

    st.subheader("Save this voice")
    voice_name = st.text_input(
        "Voice Name",
        value=st.session_state.get("voice_name_input", ""),
        key="save_voice_name",
    )
    if st.button("💾 Save Voice"):
        if not voice_name.strip():
            st.error("Please enter a name for this voice.")
        elif name_exists(voice_name.strip()):
            st.error(f"A voice named '{voice_name.strip()}' already exists. Please choose a different name.")
        else:
            try:
                resp = requests.post(
                    f"{LOCOL_API_URL}/api/voices",
                    json={"name": voice_name.strip(), "voice_prompt": st.session_state.voice_prompt},
                    headers=get_api_headers(),
                    timeout=10,
                )
                if resp.status_code == 200 and resp.json().get("success"):
                    st.success(f"Voice '{voice_name.strip()}' saved!")
                    del st.session_state["voice_prompt"]
                    st.session_state.pop("analyzed_username", None)
                    st.session_state.pop("voice_name_input", None)
                    st.session_state.pop("voices_cache", None)
                    st.rerun()
                else:
                    st.error(f"Failed to save: {resp.text}")
            except Exception as e:
                st.error(f"Error saving voice: {str(e)}")

st.divider()

# ── Section 2: Create a voice by hand ─────────────────────────────────────────

st.subheader("✍️ Create a voice")
st.write(
    "Describe how the writing should sound, as instructions to the AI. The more "
    "specific you are, the less generic the drafts: sentence length and structure, "
    "tone (dry, earnest, sarcastic), whether it makes jokes and what kind, the "
    "vocabulary and jargon it uses, and habits of punctuation — caps for emphasis, "
    "ellipses, emojis. Say what it should *never* do as well."
)

with st.form("create_voice_form", clear_on_submit=True):
    new_voice_name = st.text_input("Voice Name", placeholder="e.g. My Reddit voice")
    new_voice_prompt = st.text_area(
        "Voice Prompt",
        height=250,
        placeholder=(
            "Write in short, plain sentences — rarely more than 20 words. Be direct and "
            "a little dry; understate rather than exaggerate. No marketing language, no "
            "exclamation marks, no emojis. Use contractions. Open with the point rather "
            "than a wind-up, and end when the point is made."
        ),
    )
    created = st.form_submit_button("💾 Create Voice", type="primary")

if created:
    if not new_voice_name.strip():
        st.error("Please enter a name for this voice.")
    elif not new_voice_prompt.strip():
        st.error("Please describe the voice before saving it.")
    elif name_exists(new_voice_name.strip()):
        st.error(f"A voice named '{new_voice_name.strip()}' already exists. Please choose a different name.")
    else:
        try:
            resp = requests.post(
                f"{LOCOL_API_URL}/api/voices",
                json={"name": new_voice_name.strip(), "voice_prompt": new_voice_prompt.strip()},
                headers=get_api_headers(),
                timeout=10,
            )
            if resp.status_code == 200 and resp.json().get("success"):
                st.success(f"Voice '{new_voice_name.strip()}' created!")
                st.session_state.pop("voices_cache", None)
                st.rerun()
            else:
                st.error(f"Failed to save: {resp.text}")
        except Exception as e:
            st.error(f"Error saving voice: {str(e)}")

st.divider()

# ── Section 3: Saved Voices ───────────────────────────────────────────────────

st.subheader("Saved Voices")
st.caption(
    "Pick one of these on a campaign project — the 🎤 Voice dropdown beside "
    "🚀 Generate Content — to have its drafts written in that style."
)

if "voices_cache" not in st.session_state:
    st.session_state.voices_cache = fetch_voices()

voices = st.session_state.voices_cache

if not voices:
    st.info("No saved voices yet. Create one above to get started.")
else:
    for voice in voices:
        vid = voice["id"]
        is_editing = st.session_state.get("editing_voice_id") == vid
        is_confirming_delete = st.session_state.get("confirm_delete_id") == vid
        is_saving_as_new = st.session_state.get("saveas_mode_id") == vid

        with st.container(border=True):
            if is_editing:
                # ── Edit form ──────────────────────────────────────────────
                edit_name = st.text_input(
                    "Name",
                    value=voice["name"],
                    key=f"edit_name_{vid}",
                )
                edit_prompt = st.text_area(
                    "Voice Prompt",
                    value=voice["voice_prompt"],
                    height=200,
                    key=f"edit_prompt_{vid}",
                )

                if is_saving_as_new:
                    # ── Save as New sub-form ───────────────────────────────
                    new_name = st.text_input(
                        "New Voice Name",
                        value="",
                        key=f"saveas_name_{vid}",
                        placeholder="Enter a unique name for the new voice",
                    )
                    col_confirm, col_cancel_new = st.columns([1, 1])
                    with col_confirm:
                        if st.button("✓ Confirm Save as New", key=f"saveas_confirm_{vid}", type="primary"):
                            if not new_name.strip():
                                st.error("Please enter a name for the new voice.")
                            elif name_exists(new_name.strip()):
                                st.error(f"A voice named '{new_name.strip()}' already exists. Please choose a different name.")
                            else:
                                try:
                                    resp = requests.post(
                                        f"{LOCOL_API_URL}/api/voices",
                                        json={"name": new_name.strip(), "voice_prompt": edit_prompt.strip()},
                                        headers=get_api_headers(),
                                        timeout=10,
                                    )
                                    if resp.status_code == 200 and resp.json().get("success"):
                                        st.session_state.editing_voice_id = None
                                        st.session_state.saveas_mode_id = None
                                        st.session_state.voices_cache = fetch_voices()
                                        st.rerun()
                                    else:
                                        st.error(f"Save failed: {resp.text}")
                                except Exception as e:
                                    st.error(f"Error: {str(e)}")
                    with col_cancel_new:
                        if st.button("✖ Cancel New", key=f"saveas_cancel_{vid}"):
                            st.session_state.saveas_mode_id = None
                            st.rerun()
                else:
                    col_save, col_saveas, col_cancel = st.columns([1, 1.5, 1])
                    with col_save:
                        if st.button("💾 Save", key=f"save_{vid}"):
                            if not edit_name.strip():
                                st.error("Please enter a name.")
                            elif name_exists(edit_name.strip(), exclude_id=vid):
                                st.error(f"A voice named '{edit_name.strip()}' already exists. Please choose a different name.")
                            else:
                                try:
                                    resp = requests.put(
                                        f"{LOCOL_API_URL}/api/voices/{vid}",
                                        json={"name": edit_name.strip(), "voice_prompt": edit_prompt.strip()},
                                        headers=get_api_headers(),
                                        timeout=10,
                                    )
                                    if resp.status_code == 200 and resp.json().get("success"):
                                        st.session_state.editing_voice_id = None
                                        st.session_state.voices_cache = fetch_voices()
                                        st.rerun()
                                    else:
                                        st.error(f"Update failed: {resp.text}")
                                except Exception as e:
                                    st.error(f"Error: {str(e)}")
                    with col_saveas:
                        if st.button("📋 Save as New", key=f"saveas_{vid}"):
                            st.session_state.saveas_mode_id = vid
                            st.rerun()
                    with col_cancel:
                        if st.button("✖ Cancel", key=f"cancel_{vid}"):
                            st.session_state.editing_voice_id = None
                            st.session_state.saveas_mode_id = None
                            st.rerun()

            elif is_confirming_delete:
                # ── Delete confirmation ────────────────────────────────────
                col_info, col_yes, col_no = st.columns([3, 1, 1])
                with col_info:
                    st.warning(f"Delete **{voice['name']}**? This cannot be undone.")
                with col_yes:
                    if st.button("🗑 Yes, Delete", key=f"confirm_del_{vid}", type="primary"):
                        try:
                            resp = requests.delete(
                                f"{LOCOL_API_URL}/api/voices/{vid}",
                                headers=get_api_headers(),
                                timeout=10,
                            )
                            if resp.status_code == 200 and resp.json().get("success"):
                                st.session_state.confirm_delete_id = None
                                st.session_state.voices_cache = fetch_voices()
                                st.rerun()
                            else:
                                st.error(f"Delete failed: {resp.text}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                with col_no:
                    if st.button("✖ Cancel", key=f"cancel_del_{vid}"):
                        st.session_state.confirm_delete_id = None
                        st.rerun()

            else:
                # ── Normal row ─────────────────────────────────────────────
                col_name, col_date, col_edit, col_del = st.columns([3, 2, 1, 1])
                with col_name:
                    st.markdown(f"**{voice['name']}**")
                    st.caption(voice["voice_prompt"][:120] + ("…" if len(voice["voice_prompt"]) > 120 else ""))
                with col_date:
                    st.caption(voice.get("updated_at", "")[:16])
                with col_edit:
                    if st.button("✏ Edit", key=f"edit_{vid}"):
                        st.session_state.editing_voice_id = vid
                        st.session_state.confirm_delete_id = None
                        st.session_state.saveas_mode_id = None
                        st.rerun()
                with col_del:
                    if st.button("🗑 Delete", key=f"delete_{vid}"):
                        st.session_state.confirm_delete_id = vid
                        st.session_state.editing_voice_id = None
                        st.session_state.saveas_mode_id = None
                        st.rerun()
