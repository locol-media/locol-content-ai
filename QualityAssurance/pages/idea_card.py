"""One post idea on the Campaign Projects insights page, and its edit panel.

An idea's widgets are all keyed by the idea's own id (`edit_<id>`,
`select_<id>`, `edit_title_<id>`, ...), so the card resolves that id once - from
the `st-key-edit_<id>` class on its ✏️ Edit button - and builds everything else
from it. Tests address a card by its title, which is what a reader sees.

Opening the edit panel replaces the whole idea list with the panel: while one is
open no other card is on screen, and the app blocks sidebar navigation until it
is saved or cancelled.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import Locator, TimeoutError as PlaywrightTimeoutError

import config

from .streamlit_app import StreamlitRegion

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .campaign_projects_page import CampaignProjectsPage

#: Height of a glide-data-grid header row and of each data row, in pixels, at
#: Streamlit's default row height. Measured against the running app.
GRID_ROW_HEIGHT = 35

#: Horizontal offset of the row-marker column a selectable grid puts on the
#: left. Clicking there selects the whole row.
ROW_MARKER_X = 16


class IdeaCard:
    """A single idea: its header controls and its View Details panel."""

    def __init__(self, page: "CampaignProjectsPage", title: str):
        self.page = page
        self.title = title
        self.main: StreamlitRegion = page.main

    # ---- identity ---------------------------------------------------------

    @property
    def header(self) -> Locator:
        """The columns row holding the title, ✏️ Edit and the checkbox."""
        return self.main.root.locator(
            '[data-testid="stHorizontalBlock"]:has([class*="st-key-edit_"])'
        ).filter(
            has=self.page.page.locator(f'strong:text-is("{self.title}")')
        ).first

    @property
    def idea_id(self) -> str:
        classes = self.header.locator('[class*="st-key-edit_"]').first.get_attribute("class") or ""
        for token in classes.split():
            if token.startswith("st-key-edit_"):
                return token[len("st-key-edit_"):]
        raise AssertionError(f"Could not resolve the id of idea {self.title!r}")

    @property
    def index(self) -> int:
        """Position in the list, used to pair the card with its details panel."""
        titles = self.page.idea_titles()
        try:
            return titles.index(self.title)
        except ValueError:
            raise AssertionError(f"No idea titled {self.title!r}; found {titles}") from None

    def exists(self) -> bool:
        return self.header.count() > 0

    # ---- details ----------------------------------------------------------

    @property
    def details(self) -> Locator:
        """The View Details panel, which is expanded by default.

        Matched on `:has-text`, not `:text-is`: Streamlit renders the expander's
        chevron as a Material icon *ligature*, so the summary's text is really
        "keyboard_arrow_down\\n\\nView Details" and an exact match finds nothing.
        """
        return self.main.root.locator(
            '[data-testid="stExpander"]:has(summary:has-text("View Details"))'
        ).nth(self.index)

    def description(self) -> str:
        return self.details.locator('[data-testid="stMarkdown"]').nth(1).inner_text().strip()

    def content_type(self) -> str:
        return self._detail_field("Content Type")

    def platform(self) -> str:
        return self._detail_field("Platform")

    def goal(self) -> str:
        """The business goal this post serves.

        Unlike Content Type and Platform, which are written as "**Label:**
        value" in a single markdown, the goal's label and value are two separate
        elements in the right-hand column - so it is read positionally rather
        than by splitting on the colon.
        """
        column = self.details.locator('[data-testid="stColumn"]').nth(1)
        return column.locator('[data-testid="stMarkdown"]').nth(1).inner_text().strip()

    def _detail_field(self, label: str) -> str:
        text = self.details.locator(f'[data-testid="stMarkdown"]:has-text("{label}:")').last
        return text.inner_text().split(":", 1)[1].strip()

    def generated_content(self) -> Locator:
        """The 🤖 Generated Content section, present only once a draft exists."""
        return self.details.locator('[data-testid="stMarkdown"]:has-text("🤖 Generated Content")')

    def has_generated_content(self) -> bool:
        return self.generated_content().count() > 0

    def generation_error(self) -> Locator:
        return self.details.locator('[data-testid="stAlertContentError"]')

    def template_used(self) -> str:
        caption = self.details.locator('[data-testid="stCaptionContainer"]:has-text("Template used:")')
        return caption.inner_text().split(":", 1)[1].strip()

    # ---- header controls --------------------------------------------------

    def select_for_generation(self, selected: bool = True) -> None:
        """Tick the Generate Content checkbox."""
        self.main.set_checkbox(f"select_{self.idea_id}", selected)

    def is_selected(self) -> bool:
        return self.main.checkbox(f"select_{self.idea_id}").is_checked()

    def open_content_editor(self) -> Locator:
        """The 📝 Content Editor link, which appears only once a draft exists.

        Returns the link rather than clicking it: it opens the editor in a new
        tab, and the caller usually wants to drive that tab itself. See
        ContentEditorPage.open_from(...).
        """
        return self.main.link_button("📝 Content Editor")

    def content_editor_url(self) -> str:
        return self.open_content_editor().get_attribute("href") or ""

    def edit(self) -> "IdeaEditPanel":
        """Open the edit panel, which hides every other idea while it is open.

        The id has to be resolved *before* the click: opening the panel replaces
        the whole idea list, so `idea_id` - which reads it off this card's Edit
        button - would find nothing on a second look.
        """
        idea_id = self.idea_id
        self.main.click_key(f"edit_{idea_id}")
        return IdeaEditPanel(self.page, idea_id)


class IdeaEditPanel:
    """✏️ Edit Idea - the five editable fields plus the brainstorm section."""

    def __init__(self, page: "CampaignProjectsPage", idea_id: str):
        self.page = page
        self.idea_id = idea_id
        self.main: StreamlitRegion = page.main

    # ---- the form ---------------------------------------------------------

    def set_title(self, value: str) -> None:
        self.main.fill(f"edit_title_{self.idea_id}", value)

    def set_description(self, value: str) -> None:
        self.main.fill(f"edit_desc_{self.idea_id}", value)

    def set_content_type(self, value: str) -> None:
        self.main.select(f"edit_content_type_{self.idea_id}", value)

    def set_platform(self, value: str) -> None:
        self.main.fill(f"edit_platform_{self.idea_id}", value)

    def set_goal(self, value: str) -> None:
        self.main.fill(f"edit_goal_{self.idea_id}", value)

    def title(self) -> str:
        return self.main.value(f"edit_title_{self.idea_id}")

    def save(self) -> None:
        self.main.click("💾 Save Changes")

    def cancel(self) -> None:
        self.main.click("❌ Cancel")

    def delete(self) -> None:
        self.main.click("🗑️ Delete")

    # ---- 💡 Brainstorm Content Snippet ------------------------------------

    def set_brainstorm_prompt(self, prompt: str) -> None:
        """Set the prompt, committing it before the button can be clicked.

        This one has to commit: the 🧠 button reads the prompt on the server, so
        a value still sitting unsent in the browser reads as empty and the app
        answers with "Please enter a brainstorming prompt".
        """
        self.main.fill_and_commit(f"brainstorm_prompt_{self.idea_id}", prompt)

    def choose_voice(self, voice_name: str) -> None:
        """The 🎤 Voice picker inside the panel.

        Shares the project-level selection with the one beside 🚀 Generate
        Content, so changing it here changes it there too.
        """
        self.main.select(f"brainstorm_voice_{self.idea_id}", voice_name)

    def selected_voice(self) -> str:
        return self.main.selected_option(f"brainstorm_voice_{self.idea_id}")

    def voice_options(self) -> list[str]:
        return self.main.options(f"brainstorm_voice_{self.idea_id}")

    def brainstorm_button(self) -> Locator:
        return self.main.button_by_key(f"brainstorm_btn_{self.idea_id}")

    def brainstorm(self, prompt: str | None = None) -> None:
        """Run the brainstorm and wait out the AI call."""
        if prompt is not None:
            self.set_brainstorm_prompt(prompt)
        self.brainstorm_button().click()
        self.page.wait_until_idle(timeout=config.LLM_TIMEOUT)

    def response(self) -> str:
        return self.main.value(f"brainstorm_result_{self.idea_id}")

    def empty_prompt_warning(self) -> Locator:
        return self.main.warning("Please enter a brainstorming prompt")

    # ---- Previous Content Snippets ---------------------------------------
    #
    # st.dataframe draws itself on a canvas (glide-data-grid), so there is no
    # DOM to click. It does keep a parallel accessibility tree - a real <table>
    # of [role="row"] / [role="gridcell"] elements carrying the cell text - but
    # those elements are hidden, which makes them readable and *not* clickable.
    # Hence: read through the a11y tree, select through the canvas.

    @property
    def snippets_grid(self) -> Locator:
        return self.main.widget(f"brainstorm_snippets_grid_{self.idea_id}")

    def snippet_count(self) -> int:
        """Rows in the Previous Content Snippets grid, header excluded."""
        if not self.snippets_grid.count():
            return 0
        return max(0, self.snippets_grid.locator('[role="row"]').count() - 1)

    def wait_for_snippets(self, minimum: int = 1, timeout: int | None = None) -> bool:
        """Wait for the grid to have rendered at least `minimum` rows.

        Needed because the accessibility rows are built by the grid *after*
        Streamlit itself has gone idle, so counting the moment a rerun finishes
        can see an empty grid that fills in a tick later. Returns whether the
        rows arrived rather than raising, so a caller can report "no snippets"
        as a result instead of a crash.
        """
        try:
            self.snippets_grid.locator(
                f'[role="row"][aria-rowindex="{minimum + 1}"]'
            ).first.wait_for(state="attached", timeout=timeout or config.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            return False

    def snippet_row(self, row: int) -> list[str]:
        """One past snippet as [datetime, prompt, content snippet].

        Read with `text_content()` because the accessibility rows are hidden.
        """
        cells = self.snippets_grid.locator(
            f'[role="row"][aria-rowindex="{row + 2}"] [role="gridcell"]'
        )
        return [(cells.nth(i).text_content() or "").strip() for i in range(cells.count())]

    def open_snippet(self, row: int) -> None:
        """Load a past snippet back into the prompt and response fields.

        Clicked at the row's offset, header and rows both being GRID_ROW_HEIGHT
        tall, so row 0's centre sits one and a half rows down. Two details that
        are easy to get wrong:

        * the click goes to the *scroller*, which overlays the canvas and takes
          the pointer events - clicking the canvas is refused as intercepted.
          It is identified by class (`.stDataFrameGlideDataEditor`), not by a
          testid, despite the name looking like one;
        * it lands in the row-marker column on the left rather than in a data
          cell, because the grid is in single-row selection mode and clicking a
          cell only moves the cursor.
        """
        scroller = self.snippets_grid.locator(".stDataFrameGlideDataEditor").first
        scroller.click(position={
            "x": ROW_MARKER_X,
            "y": GRID_ROW_HEIGHT * (row + 1) + GRID_ROW_HEIGHT / 2,
        })
        self.page.wait_until_idle()

    def selected_snippet_row(self) -> int | None:
        """Which snippet row is selected, or None."""
        selected = self.snippets_grid.locator('[role="row"][aria-selected="true"]')
        if not selected.count():
            return None
        return int(selected.first.get_attribute("aria-rowindex")) - 2
