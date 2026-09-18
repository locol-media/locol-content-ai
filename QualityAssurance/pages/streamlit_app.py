"""Base classes every Streamlit page object is built on.

Why this layer exists
---------------------
Streamlit's DOM is generated, so the usual Playwright idioms do not survive
contact with it. Four facts drive every locator strategy below, and all four
were verified against the running app (Streamlit 1.49.1):

1. **Widgets given a `key=` get a `st-key-<key>` class** on their element
   container. That is the only stable, human-chosen hook Streamlit offers, so it
   is the preferred way to address anything. The two surveys pass each question's
   YAML field key straight through to the widget, which means a question is
   addressable as `st-key-<field_key>` (`business_name`, `industry`, ...) rather
   than by its prose.

2. **A button with `help=` renders twice** - once inside a
   `stTooltipHoverTarget` and once in a hidden sibling. Every button locator
   therefore filters on `:visible`, or strict mode fails on the duplicate.

3. **Button labels live in a nested `<p>`,** and the role-name match Playwright
   would otherwise use is a substring match, so "Next ➡️" would also match a
   longer label containing it. Buttons are matched on `p:text-is(...)` instead,
   which is exact.

4. **Widget labels reach the DOM as the field's `aria-label`** - including the
   escaped ` \\*` that marks a required question. Label-based lookup therefore
   has to reproduce that escape, which is the second reason to prefer keys.

One behaviour worth knowing before writing a test: authentication lives in
`st.session_state`, so **a full page load signs the session out**. Move between
pages with `Sidebar`, not `page.goto`.

Waiting
-------
Streamlit reruns the entire script on each interaction and swaps the DOM out
underneath you. `wait_until_idle()` waits for the "Running" status widget to
clear and for every element container to drop its `data-stale` flag, which is
what makes a click-then-assert sequence reliable.
"""
from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

import config

# Streamlit's own test hook: "initial", "running" or "notRunning".
SCRIPT_IDLE = '[data-testid="stApp"][data-test-script-state="notRunning"]'

# Streamlit greys out containers whose content is being recomputed.
STALE_CONTAINER = '[data-testid="stElementContainer"][data-stale="true"]'

# An interaction reaches the server over a websocket, so the app takes a moment
# to flip into "running". Sampling the state immediately after a click would
# see the *previous* run's "notRunning" and return before anything had
# re-rendered - which is exactly how a page object goes flaky.
SETTLE_MS = 250

# Both st.selectbox and st.multiselect render their options into this portal.
DROPDOWN = '[data-testid="stSelectboxVirtualDropdown"]'

ALERT_KINDS = ("Success", "Info", "Warning", "Error")


def _quote(text: str) -> str:
    """Escape a string for use inside a CSS `:text-is("...")` argument."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


class StreamlitRegion:
    """Widget accessors scoped to one part of the page (main area or sidebar).

    Everything a page object needs to touch a widget lives here, so the page
    objects themselves stay a readable list of what the page contains rather
    than a pile of selector strings.
    """

    def __init__(self, page: Page, root: Locator):
        self.page = page
        self.root = root

    # ---- generic ----------------------------------------------------------

    def widget(self, key: str) -> Locator:
        """The container of a widget created with `key=<key>`."""
        return self.root.locator(f".st-key-{key}")

    def text(self, value: str) -> Locator:
        return self.root.get_by_text(value)

    def heading(self, value: str) -> Locator:
        return self.root.locator("h1, h2, h3, h4").filter(has_text=value)

    # ---- buttons ----------------------------------------------------------

    def button(self, label: str) -> Locator:
        """A button by its exact visible label, e.g. `button("💾 Save Page")`.

        Matches the label exactly (whitespace normalised) so "Next ➡️" cannot
        also pick up a longer label containing it.
        """
        return self.root.locator(
            f'button:visible:has(p:text-is("{_quote(label)}"))'
        )

    def button_by_key(self, key: str) -> Locator:
        """A button by the `key=` it was created with - the stabler form."""
        return self.widget(key).locator("button:visible")

    def link_button(self, label: str) -> Locator:
        """An `st.link_button`, which renders an anchor rather than a button."""
        return self.root.locator(
            f'[data-testid="stLinkButton"] a:visible:has(p:text-is("{_quote(label)}"))'
        )

    def click(self, label: str) -> None:
        self.button(label).click()
        self.wait_until_idle()

    def click_key(self, key: str) -> None:
        self.button_by_key(key).click()
        self.wait_until_idle()

    # ---- text entry -------------------------------------------------------

    def input(self, key: str) -> Locator:
        """The `<input>` or `<textarea>` of a keyed text widget."""
        return self.widget(key).locator("input, textarea")

    def input_by_label(self, label: str) -> Locator:
        """Fallback for widgets created without a key.

        Streamlit copies the widget's label into the field's `aria-label`, so
        this is exact-matched against that. Required questions carry a literal
        ` \\*` suffix in their label - pass it, or use the keyed accessor.
        """
        return self.root.get_by_label(label, exact=True)

    def fill(self, key: str, value: str) -> None:
        self.input(key).fill(value)

    def fill_and_commit(self, key: str, value: str) -> None:
        """Fill a field and hand its value to the server before moving on.

        Streamlit only sends a text widget's value when it loses focus, so a
        fill immediately followed by a button click can race - the click lands
        before the value arrives and the script sees the *old* text. Blurring
        with Tab (rather than Enter, which would submit a form or add a newline
        to a text area) forces the round trip first.
        """
        field = self.input(key)
        field.fill(value)
        field.press("Tab")
        self.wait_until_idle()

    def value(self, key: str) -> str:
        return self.input(key).input_value()

    # ---- selectbox --------------------------------------------------------

    def select(self, key: str, option: str) -> None:
        """Choose an option in a keyed `st.selectbox`."""
        self.select_in(self.widget(key), option)

    def select_in(self, widget: Locator, option: str) -> None:
        """Choose an option in a selectbox located some other way.

        For the widgets Streamlit gives no key - the Content Type dropdown on
        the add-idea form, say - which have to be found through their form or
        expander instead.

        The list is virtualised, so the option is narrowed by typing before it
        is clicked rather than scrolled to. Anything that skips that step works
        only until the option it wants falls outside the rendered window.
        """
        field = widget.locator('input[role="combobox"]')
        field.click()
        field.type(option, delay=10)
        self.option(option).click()
        self.wait_until_idle()

    def selected_option(self, key: str) -> str:
        """The option currently shown in a selectbox."""
        return self.widget(key).locator('[data-baseweb="select"]').inner_text().strip()

    def options(self, key: str) -> list[str]:
        """Every option a keyed selectbox offers, in order.

        Opens the dropdown and closes it again, leaving the selection alone. The
        list is virtualised, so this only sees the rendered window - fine for the
        short lists it is used on, not for scrolling ones.
        """
        field = self.widget(key).locator('input[role="combobox"]')
        field.click()
        labels = [
            text.strip()
            for text in self.page.locator(f'{DROPDOWN} [role="option"]').all_inner_texts()
        ]
        field.press("Escape")
        self.wait_until_idle()
        return labels

    def option(self, label: str) -> Locator:
        """One option inside the open dropdown portal."""
        return self.page.locator(f'{DROPDOWN} [role="option"]').filter(
            has_text=re.compile(rf"^\s*{re.escape(label)}\s*$")
        )

    # ---- multiselect ------------------------------------------------------

    def multiselect_add(self, key: str, option: str) -> None:
        """Add one option, if it is not already chosen.

        A multiselect drops options it has already selected from its dropdown,
        so re-adding one would hang waiting for an option that is not there -
        which is what happens whenever a script is run twice over the same
        account. Checking the chosen values first makes this idempotent.
        """
        if option in self.multiselect_values(key):
            return
        field = self.widget(key).locator("input")
        field.click()
        field.type(option, delay=10)
        self.option(option).click()
        self.wait_until_idle()

    def multiselect_values(self, key: str) -> list[str]:
        tags = self.widget(key).locator('span[data-baseweb="tag"]')
        return [tags.nth(i).inner_text().strip() for i in range(tags.count())]

    def multiselect_remove(self, key: str, option: str) -> None:
        tag = self.widget(key).locator(
            f'span[data-baseweb="tag"]:has-text("{_quote(option)}")'
        )
        tag.locator('[role="presentation"], svg').last.click()
        self.wait_until_idle()

    # ---- checkbox ---------------------------------------------------------

    def checkbox(self, key: str) -> Locator:
        return self.widget(key).locator('[data-testid="stCheckbox"] input')

    def set_checkbox(self, key: str, checked: bool = True) -> None:
        """Tick or untick a checkbox.

        The real `<input>` is visually hidden behind BaseWeb's styled label, so
        it is toggled through the label rather than with `check()`.
        """
        if self.checkbox(key).is_checked() != checked:
            self.widget(key).locator('[data-testid="stCheckbox"] label').click()
            self.wait_until_idle()

    # ---- containers -------------------------------------------------------

    def expander(self, label: str) -> Locator:
        """An `st.expander` addressed by its header text."""
        return self.root.locator('[data-testid="stExpander"]').filter(has_text=label)

    def expand(self, label: str) -> Locator:
        """Open an expander if it is closed, and return it."""
        expander = self.expander(label).first
        summary = expander.locator("summary")
        if summary.get_attribute("aria-expanded") != "true":
            summary.click()
            self.wait_until_idle()
        return expander

    def tab(self, label: str) -> Locator:
        return self.root.locator('[data-testid="stTab"]').filter(has_text=label)

    def open_tab(self, label: str) -> None:
        self.tab(label).click()
        self.wait_until_idle()

    def form(self, label: str) -> Locator:
        """The `st.form` containing the given text - forms are anonymous in the DOM."""
        return self.root.locator('[data-testid="stForm"]').filter(has_text=label)

    # ---- feedback ---------------------------------------------------------

    def alert(self, kind: str, text: str | None = None) -> Locator:
        """`st.success` / `st.info` / `st.warning` / `st.error` output."""
        if kind not in ALERT_KINDS:
            raise ValueError(f"kind must be one of {ALERT_KINDS}, got {kind!r}")
        alerts = self.root.locator(f'[data-testid="stAlertContent{kind}"]')
        return alerts.filter(has_text=text) if text else alerts

    def success(self, text: str | None = None) -> Locator:
        return self.alert("Success", text)

    def info(self, text: str | None = None) -> Locator:
        return self.alert("Info", text)

    def warning(self, text: str | None = None) -> Locator:
        return self.alert("Warning", text)

    def error(self, text: str | None = None) -> Locator:
        return self.alert("Error", text)

    def errors(self) -> list[str]:
        """Every error currently on screen - useful in failure messages.

        Read with `text_content()`, not `inner_text()`: an alert rendered inside
        an expander that has since collapsed is still in the DOM but no longer
        rendered, and `inner_text()` would report it as an empty string - the
        worst possible answer for something whose whole job is diagnostics.
        """
        errors = self.alert("Error")
        return [(errors.nth(i).text_content() or "").strip() for i in range(errors.count())]

    def alert_text(self, locator: Locator) -> str:
        """The text of one alert, whether or not it is currently rendered."""
        return (locator.first.text_content() or "").strip()

    # ---- waiting ----------------------------------------------------------

    def wait_until_idle(self, timeout: int | None = None) -> None:
        StreamlitPage.wait_for_rerun(self.page, timeout)


class StreamlitPage:
    """One page of the Streamlit app.

    Subclasses set `path` (the route `st.navigation` gives the page) and expose
    the page's own vocabulary on top of `self.main` / `self.sidebar`.
    """

    #: Route relative to the app root, as registered in Web/src/main.py.
    path: str = "/"

    #: Text that must be present once the page has finished loading.
    title_text: str = ""

    def __init__(self, page: Page, base_url: str | None = None):
        self.page = page
        self.base_url = (base_url or config.WEB_URL).rstrip("/")
        self.main = StreamlitRegion(page, page.locator('[data-testid="stMain"]'))
        self.sidebar = StreamlitRegion(page, page.locator('[data-testid="stSidebar"]'))

    # ---- lifecycle --------------------------------------------------------

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.path}"

    def open(self) -> "StreamlitPage":
        """Load this page's route directly.

        Only useful for the landing page: a page load starts a fresh Streamlit
        session, and because `authenticated` lives in session state, the app
        signs you out and renders the landing page whatever the route says.
        Reach the other pages through `Sidebar` instead.
        """
        self.page.goto(self.url)
        self.wait_until_loaded()
        return self

    def wait_until_loaded(self, timeout: int | None = None) -> "StreamlitPage":
        self.wait_for_rerun(self.page, timeout)
        if self.title_text:
            expect(self.main.text(self.title_text).first).to_be_visible(
                timeout=timeout or config.DEFAULT_TIMEOUT
            )
        return self

    def wait_until_idle(self, timeout: int | None = None) -> None:
        self.wait_for_rerun(self.page, timeout)

    @staticmethod
    def wait_for_rerun(page: Page, timeout: int | None = None) -> None:
        """Block until Streamlit has finished re-running the script.

        Settles first (see SETTLE_MS), then waits on two signals: the app's own
        `data-test-script-state` returning to "notRunning", and every element
        container having dropped the `data-stale` flag it wears while its
        content is being recomputed.
        """
        limit = timeout or config.DEFAULT_TIMEOUT
        page.wait_for_timeout(SETTLE_MS)
        page.wait_for_selector(SCRIPT_IDLE, state="attached", timeout=limit)
        page.wait_for_function(
            f"() => document.querySelectorAll('{STALE_CONTAINER}').length === 0",
            timeout=limit,
        )

    def wait_for_llm(self) -> None:
        """Wait out an AI call, which runs far longer than an ordinary rerun."""
        self.wait_until_idle(timeout=config.LLM_TIMEOUT)

    # ---- shared chrome ----------------------------------------------------

    def screenshot(self, path: str) -> None:
        self.page.screenshot(path=path, full_page=True)
