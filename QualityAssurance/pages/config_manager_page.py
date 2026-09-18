"""⚙️ Configuration Manager - LLMs, Channels and Prompt Templates.

Three tabs, each the same shape: an "➕ Add New ..." form at the top and one
expander per existing record containing an edit form. Add-forms use fixed keys
(`llm_new_name`, `channel_new_id`, ...); edit-forms key their fields by record
id (`llm_name_<id>`), so the record id is what identifies a row.

Every generate step in the app depends on an LLM being configured here, which
makes `llm_names()` a useful precondition check for AI tests.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from .sidebar import Sidebar
from .streamlit_app import StreamlitPage

API_STYLES = ("openai", "claude", "gemini")

TAB_LLMS = "🤖 LLMs"
TAB_CHANNELS = "📺 Channels"
TAB_PROMPTS = "📝 Prompts"


class ConfigManagerPage(StreamlitPage):
    path = "/configManager"
    title_text = "⚙️ Configuration Manager"

    def __init__(self, page: Page, base_url: str | None = None):
        super().__init__(page, base_url)
        self.nav = Sidebar(page)

    def login_required_warning(self) -> Locator:
        return self.main.warning("Please login to access the configuration manager")

    # ---- tabs -------------------------------------------------------------

    def open_llms(self) -> None:
        self.main.open_tab(TAB_LLMS)

    def open_channels(self) -> None:
        self.main.open_tab(TAB_CHANNELS)

    def open_prompts(self) -> None:
        self.main.open_tab(TAB_PROMPTS)

    # ---- 🤖 LLMs -----------------------------------------------------------

    def llm_names(self) -> list[str]:
        return self._record_names("🤖 ")

    def llm(self, name: str) -> Locator:
        """The expander for one LLM. Its header is "🤖 <name> (<model>)"."""
        return self.main.expander(f"🤖 {name}")

    def add_llm(
        self,
        name: str,
        api_style: str = "openai",
        model: str = "",
        api_key: str = "",
        api_url: str = "",
        record_id: str = "",
    ) -> None:
        """Add an LLM. Name and API Style are required; the id auto-generates."""
        self.main.expand("➕ Add New LLM")
        self.main.fill("llm_new_id", record_id)
        self.main.fill("llm_new_name", name)
        self.main.select("llm_new_api_style", api_style)
        self.main.fill("llm_new_model", model)
        self.main.fill("llm_new_api_key", api_key)
        self.main.fill("llm_new_api_url", api_url)
        self.main.button("Add LLM").click()
        self.wait_until_idle()

    def edit_llm(self, record_id: str, **fields: str) -> None:
        """Update an existing LLM, addressed by its record id.

        Accepts any of `name`, `api_style`, `model`, `api_key`, `api_url`.
        Leaving `api_key` out keeps the stored key - the field is blank on load
        and only overwrites when something is typed into it.
        """
        for field, value in fields.items():
            key = f"llm_{field}_{record_id}"
            if field == "api_style":
                self.main.select(key, value)
            else:
                self.main.fill(key, value)
        self._submit_record(f"llm_id_{record_id}", "💾 Update")

    def delete_llm(self, record_id: str) -> None:
        self._submit_record(f"llm_id_{record_id}", "🗑️ Delete")

    # ---- 📺 Channels -------------------------------------------------------

    def channel_names(self) -> list[str]:
        return self._record_names("📺 ")

    def channel(self, name: str) -> Locator:
        return self.main.expander(f"📺 {name}")

    def add_channel(self, name: str, parent: str = "", record_id: str = "") -> None:
        self.main.expand("➕ Add New Channel")
        self.main.fill("channel_new_id", record_id)
        self.main.fill("channel_new_name", name)
        self.main.fill("channel_new_parent", parent)
        self.main.button("Add Channel").click()
        self.wait_until_idle()

    def delete_channel(self, record_id: str) -> None:
        self._submit_record(f"channel_id_{record_id}", "🗑️ Delete")

    # ---- 📝 Prompts --------------------------------------------------------

    def prompt_names(self) -> list[str]:
        return self._record_names("📝 ")

    def prompt(self, name: str) -> Locator:
        return self.main.expander(f"📝 {name}")

    def add_prompt(self, name: str, template: str, tags: str = "", record_id: str = "") -> None:
        """Add a prompt template. Name and Template are both required.

        `tags` is the raw comma-separated string the form takes.
        """
        self.main.expand("➕ Add New Prompt")
        self.main.fill("prompt_new_id", record_id)
        self.main.fill("prompt_new_name", name)
        self.main.fill("prompt_new_template", template)
        self.main.fill("prompt_new_tags", tags)
        self.main.button("Add Prompt").click()
        self.wait_until_idle()

    def edit_prompt(self, record_id: str, **fields: str) -> None:
        """Update a prompt, by record id. Accepts `name`, `template`, `tags`."""
        for field, value in fields.items():
            self.main.fill(f"prompt_{field}_{record_id}", value)
        self._submit_record(f"prompt_id_{record_id}", "💾 Update")

    def delete_prompt(self, record_id: str) -> None:
        self._submit_record(f"prompt_id_{record_id}", "🗑️ Delete")

    # ---- shared -----------------------------------------------------------

    def record_id(self, expander: Locator) -> str:
        """The id shown in a record's read-only ID field."""
        return expander.locator('input[disabled]').first.input_value()

    def _record_names(self, prefix: str) -> list[str]:
        summaries = self.main.root.locator('[data-testid="stExpander"] summary')
        names = []
        for i in range(summaries.count()):
            text = summaries.nth(i).inner_text().strip()
            if prefix in text:
                name = text.split(prefix, 1)[1].strip()
                names.append(name.split(" (")[0] if prefix == "🤖 " else name)
        return names

    def _submit_record(self, anchor_key: str, label: str) -> None:
        """Click a submit button inside one record's edit form.

        Submit buttons are keyed after their form and label with punctuation
        replaced by dashes (`FormSubmitter-edit_llm_<id>----Update`), which is
        both brittle and unreadable, so the form is identified by the read-only
        ID field it contains (`llm_id_<id>`) and the button by its text.
        """
        form = self.main.root.locator(
            f'[data-testid="stForm"]:has(.st-key-{anchor_key})'
        ).first
        form.locator(f'button:visible:has(p:text-is("{label}"))').click()
        self.wait_until_idle()
