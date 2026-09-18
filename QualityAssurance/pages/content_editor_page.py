"""Stage 4 - the Content Editor.

Not a Streamlit page: a static Stencil/Quill app served by BackEnd at
`/www/index.html`, opened in a new tab from an idea that already has a draft.
Its plain ids make it far simpler to address than the Streamlit surfaces - the
only real subtlety is the session token, which rides in the URL *fragment*
(`#jwt=...`) so it never reaches a server log, and which the page strips out of
the URL as soon as it has read it.

Quill keeps its text in a contenteditable `.ql-editor` rather than a form field,
so text is read and written through that element, not `fill()` on an input.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

import config


class ContentEditorPage:
    """The editor tab: content pane, prompt input, history and prompt editor."""

    #: intro.js's backdrop. It covers the whole page and swallows every click,
    #: so nothing here works until the tour is dismissed.
    TOUR_OVERLAY = ".introjs-overlay"

    def __init__(self, page: Page, base_url: str | None = None):
        self.page = page
        self.base_url = (base_url or config.API_URL).rstrip("/")
        #: Whether a guided tour was up when this page finished loading.
        self.tour_seen = False

    # ---- opening ----------------------------------------------------------

    @classmethod
    def open_from(cls, idea_card, base_url: str | None = None) -> "ContentEditorPage":
        """Follow an idea's 📝 Content Editor link and return the new tab.

        The link targets a new tab, so the popup is captured rather than
        waiting on the current page to navigate.
        """
        context = idea_card.page.page.context
        with context.expect_page() as new_tab:
            idea_card.open_content_editor().click()
        editor = cls(new_tab.value, base_url)
        editor.wait_until_loaded()
        return editor

    def open(self, project_id: str, item_id: str, jwt: str) -> "ContentEditorPage":
        """Load the editor directly for one idea.

        Mirrors the URL projectSurvey.py builds, token in the fragment included.
        """
        self.page.goto(
            f"{self.base_url}/www/index.html"
            f"?project_id={project_id}&item_id={item_id}#jwt={jwt}"
        )
        return self.wait_until_loaded()

    def wait_until_loaded(self, timeout: int | None = None) -> "ContentEditorPage":
        expect(self.content_editor).to_be_visible(timeout=timeout or config.DEFAULT_TIMEOUT)
        self.tour_seen = self.dismiss_tour(timeout)
        return self

    def dismiss_tour(self, timeout: int | None = None) -> bool:
        """Close the guided tour, and report whether there was one to close.

        getting-started.js calls `introJs().start()` unconditionally on every
        load - nothing is remembered between visits - so the tour is up every
        time the editor is opened, and its overlay intercepts every click until
        it goes away. Dismissed through the tooltip's ✕, falling back to Escape
        (`exitOnEsc` is on), because the overlay is exactly what a click would
        have to pass through.
        """
        skip = self.page.locator(".introjs-skipbutton")
        overlay = self.page.locator(self.TOUR_OVERLAY)
        if not overlay.count() and not skip.count():
            return False

        if skip.count():
            skip.first.click()
        else:
            self.page.keyboard.press("Escape")
        expect(overlay).to_have_count(0, timeout=timeout or config.DEFAULT_TIMEOUT)
        return True

    def tour_visible(self) -> bool:
        return self.page.locator(self.TOUR_OVERLAY).count() > 0

    def wait_until_item_loaded(self, timeout: int | None = None) -> "ContentEditorPage":
        """Wait for the item in the URL to finish selecting itself.

        `wait_until_loaded()` returns as soon as the editor pane exists, which is
        well before the page is usable: dynamic-dropdowns.js selects the item
        behind two chained `setTimeout`s (100ms then 300ms), and only once it is
        selected does it look up the item's channel/LLM combination and load the
        draft. Until then every dropdown still reads "None" and both Quill panes
        are empty, so anything checked immediately after opening is checked
        against an editor that has not finished starting up.
        """
        expect(self.item_dropdown.locator(".locol-single-entry")).not_to_have_text(
            "None", timeout=timeout or config.DEFAULT_TIMEOUT
        )
        return self

    def wait_for_draft(self, timeout: int | None = None) -> "ContentEditorPage":
        """Wait for the Content Editor pane to hold something.

        Only meaningful for an item that already has a draft; an item with no
        saved content legitimately stays empty.
        """
        expect(self.content_editor).not_to_be_empty(
            timeout=timeout or config.DEFAULT_TIMEOUT
        )
        return self

    # ---- panes ------------------------------------------------------------

    @property
    def content_editor(self) -> Locator:
        """The Content Editor pane's editable area."""
        return self.page.locator("#quill-editor .ql-editor")

    @property
    def prompt_editor(self) -> Locator:
        return self.page.locator("#prompt-editor .ql-editor")

    @property
    def history(self) -> Locator:
        return self.page.locator("#view .ql-editor")

    @property
    def prompt_input(self) -> Locator:
        """The Prompt Input pane, whose fields are generated by dynamic-fields.js."""
        return self.page.locator("#content_fields")

    @property
    def prompt_window(self) -> Locator:
        return self.page.locator("#prompt_window_scroll")

    @property
    def word_count(self) -> Locator:
        return self.page.locator("#counter")

    # ---- dropdowns --------------------------------------------------------

    @property
    def project_dropdown(self) -> Locator:
        return self.page.locator("#locol-project")

    @property
    def item_dropdown(self) -> Locator:
        return self.page.locator("#locol-item")

    @property
    def channel_dropdown(self) -> Locator:
        return self.page.locator("#locol-channel")

    @property
    def llm_dropdown(self) -> Locator:
        return self.page.locator("#locol-llm")

    @staticmethod
    def selection(dropdown: Locator) -> str:
        """What one dropdown is currently showing, or "None".

        These are custom divs built by dynamic-dropdown-class.js, not `<select>`
        elements, so there is no value to read: the current choice is the text of
        the `.locol-single-entry` div, which the widget initialises to "None" and
        rewrites as entries are picked.
        """
        return (dropdown.locator(".locol-single-entry").first.inner_text() or "").strip()

    def selected_project(self) -> str:
        return self.selection(self.project_dropdown)

    def selected_item(self) -> str:
        return self.selection(self.item_dropdown)

    def selected_channel(self) -> str:
        return self.selection(self.channel_dropdown)

    def selected_llm(self) -> str:
        return self.selection(self.llm_dropdown)

    # ---- content ----------------------------------------------------------

    def text(self) -> str:
        return self.content_editor.inner_text().strip()

    def html(self) -> str:
        return self.content_editor.inner_html()

    def set_text(self, value: str) -> None:
        """Replace the draft. Typed rather than filled, so Quill sees the edit."""
        self.content_editor.click()
        self.page.keyboard.press("ControlOrMeta+a")
        self.page.keyboard.type(value)

    def append_text(self, value: str) -> None:
        self.content_editor.click()
        self.page.keyboard.press("ControlOrMeta+End")
        self.page.keyboard.type(value)

    def set_prompt(self, value: str) -> None:
        self.prompt_editor.click()
        self.page.keyboard.press("ControlOrMeta+a")
        self.page.keyboard.type(value)

    # ---- actions ----------------------------------------------------------

    @property
    def submit_prompt_button(self) -> Locator:
        return self.page.locator("#submit_prompt")

    @property
    def save_content_button(self) -> Locator:
        return self.page.locator("#save_content")

    def submit_prompt(self) -> None:
        """Re-prompt the AI to rework the draft."""
        self.submit_prompt_button.click()
        self.page.wait_for_load_state("networkidle", timeout=config.LLM_TIMEOUT)

    def save_content(self) -> None:
        """Save the draft back to the idea it came from.

        The project page picks the change up through 🔄 Refresh Content.
        """
        self.save_content_button.click()
        self.page.wait_for_load_state("networkidle", timeout=config.DEFAULT_TIMEOUT)

    def close(self) -> None:
        self.page.close()
