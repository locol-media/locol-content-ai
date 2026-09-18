import streamlit as st
import requests
import uuid
from datetime import datetime

from apiClient import LOCOL_API_URL, get_api_headers as get_auth_headers

# =============================================================================
# API Functions for LLMs
# =============================================================================

def fetch_llms():
    """Fetch all LLM records"""
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/llms",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        st.error(f"Failed to fetch LLMs ({response.status_code}): {response.text}")
        return []
    except Exception as e:
        st.error(f"Error fetching LLMs: {str(e)}")
        return []

def create_llm(data):
    """Create a new LLM record"""
    try:
        response = requests.post(
            f"{LOCOL_API_URL}/api/llms",
            json=data,
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return True, None
        try:
            detail = response.json().get("detail", "Failed to add LLM")
        except Exception:
            detail = "Failed to add LLM"
        return False, detail
    except Exception as e:
        return False, f"Error creating LLM: {str(e)}"

def update_llm(llm_id, data):
    """Update an LLM record"""
    try:
        response = requests.put(
            f"{LOCOL_API_URL}/api/llms/{llm_id}",
            json=data,
            headers=get_auth_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error updating LLM: {str(e)}")
        return False

def delete_llm(llm_id):
    """Delete an LLM record"""
    try:
        response = requests.delete(
            f"{LOCOL_API_URL}/api/llms/{llm_id}",
            headers=get_auth_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting LLM: {str(e)}")
        return False

# =============================================================================
# API Functions for Channels
# =============================================================================

def fetch_channels():
    """Fetch all channel records"""
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/channels",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        st.error(f"Failed to fetch channels ({response.status_code}): {response.text}")
        return []
    except Exception as e:
        st.error(f"Error fetching channels: {str(e)}")
        return []

def create_channel(data):
    """Create a new channel record"""
    try:
        response = requests.post(
            f"{LOCOL_API_URL}/api/channels",
            json=data,
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return True, None
        try:
            detail = response.json().get("detail", "Failed to add channel")
        except Exception:
            detail = "Failed to add channel"
        return False, detail
    except Exception as e:
        return False, f"Error creating channel: {str(e)}"

def update_channel(channel_id, data):
    """Update a channel record"""
    try:
        response = requests.put(
            f"{LOCOL_API_URL}/api/channels/{channel_id}",
            json=data,
            headers=get_auth_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error updating channel: {str(e)}")
        return False

def delete_channel(channel_id):
    """Delete a channel record"""
    try:
        response = requests.delete(
            f"{LOCOL_API_URL}/api/channels/{channel_id}",
            headers=get_auth_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting channel: {str(e)}")
        return False

# =============================================================================
# API Functions for Prompts
# =============================================================================

def fetch_prompts():
    """Fetch all prompt records"""
    try:
        response = requests.get(
            f"{LOCOL_API_URL}/api/prompts",
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        st.error(f"Failed to fetch prompts ({response.status_code}): {response.text}")
        return []
    except Exception as e:
        st.error(f"Error fetching prompts: {str(e)}")
        return []

def create_prompt(data):
    """Create a new prompt record"""
    try:
        response = requests.post(
            f"{LOCOL_API_URL}/api/prompts",
            json=data,
            headers=get_auth_headers(),
            timeout=10
        )
        if response.status_code == 200:
            return True, None
        try:
            detail = response.json().get("detail", "Failed to add prompt")
        except Exception:
            detail = "Failed to add prompt"
        return False, detail
    except Exception as e:
        return False, f"Error creating prompt: {str(e)}"

def update_prompt(prompt_id, data):
    """Update a prompt record"""
    try:
        response = requests.put(
            f"{LOCOL_API_URL}/api/prompts/{prompt_id}",
            json=data,
            headers=get_auth_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error updating prompt: {str(e)}")
        return False

def delete_prompt(prompt_id):
    """Delete a prompt record"""
    try:
        response = requests.delete(
            f"{LOCOL_API_URL}/api/prompts/{prompt_id}",
            headers=get_auth_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting prompt: {str(e)}")
        return False

# =============================================================================
# UI Components
# =============================================================================

def render_llms_tab():
    """Render the LLMs management tab"""
    st.subheader("LLM Configurations")

    # Clear the Add New LLM form fields before they're instantiated below,
    # if the previous run just successfully submitted it
    if st.session_state.pop("llm_form_clear", False):
        for k in ["llm_new_id", "llm_new_name", "llm_new_api_style", "llm_new_model", "llm_new_api_key", "llm_new_api_url"]:
            st.session_state.pop(k, None)

    # Fetch current data
    llms = fetch_llms()

    # Add new LLM form
    with st.expander("➕ Add New LLM", expanded=False):
        with st.form("add_llm_form"):
            # ID field (optional - will auto-generate if empty)
            new_id = st.text_input("ID (optional - leave empty to auto-generate)",
                                   key="llm_new_id",
                                   help="Unique identifier for this LLM. Leave empty to auto-generate a UUID.")

            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Name *", key="llm_new_name")
                new_api_style = st.selectbox("API Style *", ["openai", "claude", "gemini"], key="llm_new_api_style")
                new_model = st.text_input("Model", key="llm_new_model")
            with col2:
                new_api_key = st.text_input("API Key", type="password", key="llm_new_api_key")
                new_api_url = st.text_input("API URL", key="llm_new_api_url")

            if st.form_submit_button("Add LLM", type="primary"):
                if new_name and new_api_style:
                    # Use custom ID if provided, otherwise generate UUID
                    llm_id = new_id.strip() if new_id.strip() else str(uuid.uuid4())

                    data = {
                        "id": llm_id,
                        "name": new_name,
                        "APIstyle": new_api_style,
                        "APIkey": new_api_key,
                        "APIurl": new_api_url,
                        "model": new_model
                    }
                    success, error_msg = create_llm(data)
                    if success:
                        st.success(f"LLM added successfully with ID: {llm_id}")
                        st.session_state["llm_form_clear"] = True
                        st.rerun()
                    else:
                        st.error(error_msg)
                else:
                    st.error("Name and API Style are required")

    # Display existing LLMs
    if llms:
        for llm in llms:
            with st.expander(f"🤖 {llm.get('name', 'Unnamed')} ({llm.get('model', 'N/A')})"):
                with st.form(f"edit_llm_{llm['id']}"):
                    # Display ID (read-only)
                    st.text_input("ID (read-only)", value=llm.get('id', ''), key=f"llm_id_{llm['id']}", disabled=True)

                    col1, col2 = st.columns(2)
                    with col1:
                        edit_name = st.text_input("Name", value=llm.get('name', ''), key=f"llm_name_{llm['id']}")
                        edit_api_style = st.selectbox(
                            "API Style",
                            ["openai", "claude", "gemini"],
                            index=["openai", "claude", "gemini"].index(llm.get('APIstyle', 'openai')) if llm.get('APIstyle') in ["openai", "claude", "gemini"] else 0,
                            key=f"llm_api_style_{llm['id']}"
                        )
                        edit_model = st.text_input("Model", value=llm.get('model', ''), key=f"llm_model_{llm['id']}")
                    with col2:
                        edit_api_key = st.text_input(
                            "API Key",
                            value="",
                            type="password",
                            placeholder=f"Unchanged ({llm.get('APIkey', '')})",
                            key=f"llm_api_key_{llm['id']}"
                        )
                        edit_api_url = st.text_input("API URL", value=llm.get('APIurl', ''), key=f"llm_api_url_{llm['id']}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Update", type="primary"):
                            data = {
                                "name": edit_name,
                                "APIstyle": edit_api_style,
                                "APIurl": edit_api_url,
                                "model": edit_model
                            }
                            if edit_api_key:
                                data["APIkey"] = edit_api_key
                            if update_llm(llm['id'], data):
                                st.success("LLM updated successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to update LLM")
                    with col2:
                        if st.form_submit_button("🗑️ Delete", type="secondary"):
                            if delete_llm(llm['id']):
                                st.success("LLM deleted successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to delete LLM")
    else:
        st.info("No LLMs configured. Add one above!")

def render_channels_tab():
    """Render the Channels management tab"""
    st.subheader("Channel Configurations")

    # Clear the Add New Channel form fields before they're instantiated below,
    # if the previous run just successfully submitted it
    if st.session_state.pop("channel_form_clear", False):
        for k in ["channel_new_id", "channel_new_name", "channel_new_parent"]:
            st.session_state.pop(k, None)

    # Fetch current data
    channels = fetch_channels()

    # Add new channel form
    with st.expander("➕ Add New Channel", expanded=False):
        with st.form("add_channel_form"):
            new_id = st.text_input("ID (optional - leave empty to auto-generate)",
                                   key="channel_new_id",
                                   help="Unique identifier for this channel. Leave empty to auto-generate a UUID.")
            new_name = st.text_input("Name *", key="channel_new_name")
            new_parent = st.text_input("Parent (optional)", key="channel_new_parent")

            if st.form_submit_button("Add Channel", type="primary"):
                if new_name:
                    channel_id = new_id.strip() if new_id.strip() else str(uuid.uuid4())

                    data = {
                        "id": channel_id,
                        "name": new_name,
                        "parent": new_parent if new_parent else None
                    }
                    success, error_msg = create_channel(data)
                    if success:
                        st.success(f"Channel added successfully with ID: {channel_id}")
                        st.session_state["channel_form_clear"] = True
                        st.rerun()
                    else:
                        st.error(error_msg)
                else:
                    st.error("Name is required")

    # Display existing channels
    if channels:
        for channel in channels:
            with st.expander(f"📺 {channel.get('name', 'Unnamed')}"):
                with st.form(f"edit_channel_{channel['id']}"):
                    st.text_input("ID (read-only)", value=channel.get('id', ''), key=f"channel_id_{channel['id']}", disabled=True)
                    edit_name = st.text_input("Name", value=channel.get('name', ''), key=f"channel_name_{channel['id']}")
                    edit_parent = st.text_input("Parent", value=channel.get('parent', '') or '', key=f"channel_parent_{channel['id']}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Update", type="primary"):
                            data = {
                                "name": edit_name,
                                "parent": edit_parent if edit_parent else None
                            }
                            if update_channel(channel['id'], data):
                                st.success("Channel updated successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to update channel")
                    with col2:
                        if st.form_submit_button("🗑️ Delete", type="secondary"):
                            if delete_channel(channel['id']):
                                st.success("Channel deleted successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to delete channel")
    else:
        st.info("No channels configured. Add one above!")

def render_prompts_tab():
    """Render the Prompts management tab"""
    st.subheader("Prompt Templates")

    # Clear the Add New Prompt form fields before they're instantiated below,
    # if the previous run just successfully submitted it
    if st.session_state.pop("prompt_form_clear", False):
        for k in ["prompt_new_id", "prompt_new_name", "prompt_new_template", "prompt_new_tags"]:
            st.session_state.pop(k, None)

    # Fetch current data
    prompts = fetch_prompts()

    # Add new prompt form
    with st.expander("➕ Add New Prompt", expanded=False):
        with st.form("add_prompt_form"):
            new_id = st.text_input("ID (optional - leave empty to auto-generate)",
                                   key="prompt_new_id",
                                   help="Unique identifier for this prompt. Leave empty to auto-generate a UUID.")
            new_name = st.text_input("Name *", key="prompt_new_name")
            new_template = st.text_area("Template *", height=200, key="prompt_new_template")
            new_tags = st.text_input("Tags (comma-separated)", key="prompt_new_tags")

            if st.form_submit_button("Add Prompt", type="primary"):
                if new_name and new_template:
                    prompt_id = new_id.strip() if new_id.strip() else str(uuid.uuid4())
                    tags_list = [tag.strip() for tag in new_tags.split(',') if tag.strip()] if new_tags else []

                    data = {
                        "id": prompt_id,
                        "name": new_name,
                        "template": new_template,
                        "tags": tags_list
                    }
                    success, error_msg = create_prompt(data)
                    if success:
                        st.success(f"Prompt added successfully with ID: {prompt_id}")
                        st.session_state["prompt_form_clear"] = True
                        st.rerun()
                    else:
                        st.error(error_msg)
                else:
                    st.error("Name and Template are required")

    # Display existing prompts
    if prompts:
        for prompt in prompts:
            with st.expander(f"📝 {prompt.get('name', 'Unnamed')}"):
                with st.form(f"edit_prompt_{prompt['id']}"):
                    st.text_input("ID (read-only)", value=prompt.get('id', ''), key=f"prompt_id_{prompt['id']}", disabled=True)
                    edit_name = st.text_input("Name", value=prompt.get('name', ''), key=f"prompt_name_{prompt['id']}")
                    edit_template = st.text_area("Template", value=prompt.get('template', ''), height=200, key=f"prompt_template_{prompt['id']}")
                    current_tags = ', '.join(prompt.get('tags', [])) if prompt.get('tags') else ''
                    edit_tags = st.text_input("Tags (comma-separated)", value=current_tags, key=f"prompt_tags_{prompt['id']}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Update", type="primary"):
                            tags_list = [tag.strip() for tag in edit_tags.split(',') if tag.strip()] if edit_tags else []
                            data = {
                                "name": edit_name,
                                "template": edit_template,
                                "tags": tags_list
                            }
                            if update_prompt(prompt['id'], data):
                                st.success("Prompt updated successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to update prompt")
                    with col2:
                        if st.form_submit_button("🗑️ Delete", type="secondary"):
                            if delete_prompt(prompt['id']):
                                st.success("Prompt deleted successfully!")
                                st.rerun()
                            else:
                                st.error("Failed to delete prompt")
    else:
        st.info("No prompts configured. Add one above!")

# =============================================================================
# Main Page
# =============================================================================

st.title("⚙️ Configuration Manager")

# Check authentication
if 'authenticated' not in st.session_state or not st.session_state.authenticated:
    st.warning("Please login to access the configuration manager.")
    st.stop()

st.markdown("Manage your LLMs, Channels, and Prompt Templates")

# Create tabs for different configuration types
tab1, tab2, tab3 = st.tabs(["🤖 LLMs", "📺 Channels", "📝 Prompts"])

with tab1:
    render_llms_tab()

with tab2:
    render_channels_tab()

with tab3:
    render_prompts_tab()
