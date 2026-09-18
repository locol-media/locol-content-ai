"""Stage 1 - Find Your Voice: create, edit, copy and delete writing-style profiles.

The Reddit analyser at the top of the page is disabled unless
`LOCOL_FIND_YOUR_VOICE_ENABLED` is set on both Web and BackEnd; shipped
configuration leaves it off, so `analyse_enabled()` reports what the run under
test actually offers rather than assuming.

Saved voices are rendered as bordered containers rather than keyed widgets, so a
voice row is found by its name and its buttons are scoped to that row.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from .sidebar import Sidebar
from .streamlit_app import StreamlitPage


class FindYourVoicePage(StreamlitPage):
    path = "/findYourVoice"
    title_text = "Find Your Voice"

    def __init__(self, page: Page, base_url: str | None = None):
        super().__init__(page, base_url)
        self.nav = Sidebar(page)

    # ---- 🔍 Analyze a Reddit account --------------------------------------

    def analyse_enabled(self) -> bool:
        return self.main.input_by_label("Reddit Username").is_enabled()

    def unavailable_warning(self) -> Locator:
        return self.main.warning("Reddit analysis is currently unavailable")

    def analyse(self, reddit_username: str) -> None:
        self.main.input_by_label("Reddit Username").fill(reddit_username)
        self.main.button("Analyze Voice").click()
        self.wait_for_llm()

    # ---- ✍️ Create a voice -------------------------------------------------

    def create_voice(self, name: str, prompt: str) -> None:
        """Fill in and submit the create form. It clears itself on success."""
        form = self.main.form("Voice Prompt")
        form.get_by_label("Voice Name", exact=True).fill(name)
        form.get_by_label("Voice Prompt", exact=True).fill(prompt)
        self.main.button_by_key("FormSubmitter-create_voice_form----Create-Voice").click()
        self.wait_until_idle()

    def created_message(self, name: str) -> Locator:
        return self.main.success(f"Voice '{name}' created!")

    def duplicate_name_error(self, name: str) -> Locator:
        return self.main.error(f"A voice named '{name}' already exists")

    # ---- Saved Voices ------------------------------------------------------

    def no_voices_message(self) -> Locator:
        return self.main.info("No saved voices yet")

    def voice_names(self) -> list[str]:
        rows = self.main.root.locator('[data-testid="stVerticalBlock"] strong')
        return [rows.nth(i).inner_text().strip() for i in range(rows.count())]

    def voice(self, name: str) -> Locator:
        """The bordered container for one saved voice.

        `st.container(border=True)` has no testid of its own in Streamlit 1.49 -
        it is an ordinary `stVerticalBlock` - so the row is the *innermost*
        block containing that name. Locators come back in document order, which
        puts ancestors first, so `.last` is the tightest match.
        """
        return self.main.root.locator('[data-testid="stVerticalBlock"]').filter(
            has=self.page.locator(f'strong:text-is("{name}")')
        ).last

    def _row_button(self, name: str, label: str) -> Locator:
        return self.voice(name).locator(
            f'button:visible:has(p:text-is("{label}"))'
        )

    def edit_voice(self, name: str) -> None:
        """Open a voice's edit form, replacing its row with Name/Voice Prompt fields."""
        self._row_button(name, "✏ Edit").click()
        self.wait_until_idle()

    def set_edited_name(self, value: str) -> None:
        self.main.root.get_by_label("Name", exact=True).fill(value)

    def set_edited_prompt(self, value: str) -> None:
        self.main.root.get_by_label("Voice Prompt", exact=True).fill(value)

    def save_edit(self) -> None:
        self.main.click("💾 Save")

    def cancel_edit(self) -> None:
        self.main.click("✖ Cancel")

    def save_as_new(self, new_name: str) -> None:
        """📋 Save as New - copy the open edit form's prompt under another name."""
        self.main.click("📋 Save as New")
        self.main.root.get_by_label("New Voice Name", exact=True).fill(new_name)
        self.main.click("✓ Confirm Save as New")

    def delete_voice(self, name: str, confirm: bool = True) -> None:
        """Delete a voice. The row turns into a confirmation before anything happens."""
        self._row_button(name, "🗑 Delete").click()
        self.wait_until_idle()
        self.main.click("🗑 Yes, Delete" if confirm else "✖ Cancel")

    def delete_confirmation(self, name: str) -> Locator:
        return self.main.warning(f"Delete {name}?")
