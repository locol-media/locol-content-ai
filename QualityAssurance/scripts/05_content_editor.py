"""05 - Stage 4: open a draft in the Content Editor, edit it, and prove it saved.

The Content Editor is the only screen in the product that is not Streamlit: a
static Quill app served by BackEnd at `/www/index.html`, opened in a new tab
from an idea that already has a draft. This script drives both apps at once -
Streamlit to reach the draft, the editor tab to change it, then Streamlit again
to confirm the change came back - and prints a pass/fail line per check rather
than stopping at the first problem.

By default it works on **its own throwaway idea**, added through ➕ Add Campaign
Idea Manually, drafted, edited and then deleted, so no real idea is touched.
That costs **one LLM call**, because a draft is this script's precondition: the
📝 Content Editor link only exists once an idea has generated content
(projectSurvey.py checks `has_generated_content`). Pass `--idea` to work on an
idea that is already drafted instead, which spends no LLM call.

Five things about the editor decide how this is written:

* **A guided tour covers the page on every load.** getting-started.js calls
  `introJs().start()` unconditionally, remembering nothing between visits, and
  its overlay intercepts every click - so the first thing any automation must do
  is dismiss it. `ContentEditorPage.wait_until_loaded()` now does, and records
  that it had to in `tour_seen`.
* **Nothing is ready when the pane appears.** dynamic-dropdowns.js selects the
  item from the URL behind two chained `setTimeout`s, and only then looks up its
  channel/LLM combination and loads the draft - so the script waits for the item
  dropdown to stop reading "None" before it checks anything.
* **The dropdowns are not `<select>`s.** They are divs whose current choice is
  the text of a `.locol-single-entry` child.
* **The channel and LLM auto-select only when the item has exactly one
  combination** in its history (`/api/check-item-llm-channel`). A freshly
  drafted idea has one, so they fill in; an idea drafted repeatedly against
  different channels would not, and the editor would open with them unset.
* **Saving adds a version rather than overwriting one.** Save Content POSTs to
  `/api/persist-content/`, which inserts a `query_history` row; the project page
  then shows the newest row's text as the idea's draft, because
  `get_project_brainstorm_ideas()` overlays it (see BackEnd/src/rag_run.py).
  That is why the edit is visible back in Streamlit after 🔄 Refresh Content,
  and why an earlier draft is never destroyed - it stays in the History pane.

Usage, from the QualityAssurance folder:

    .venv/Scripts/python scripts/05_content_editor.py
    .venv/Scripts/python scripts/05_content_editor.py --headed --slow-mo 300
    .venv/Scripts/python scripts/05_content_editor.py --project "My story"
    .venv/Scripts/python scripts/05_content_editor.py --idea "An existing drafted idea"
    .venv/Scripts/python scripts/05_content_editor.py --keep   # leave the probe idea behind

Like `03`, it reports **known defects** separately: a check whose failure is an
already-diagnosed app bug is printed but not counted against the run, so it
neither hides a real regression nor turns the run red for something understood.
If one starts passing, the script says so and the exemption should go.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Run as a plain script, so make the suite's own modules importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The app's headings are full of emoji and a Windows console defaults to cp1252,
# which cannot encode them.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright  # noqa: E402

import config  # noqa: E402
from pages import CampaignProjectsPage, ContentEditorPage, HomePage, LoginPage  # noqa: E402

STAMP = datetime.now().strftime("%H:%M:%S")

#: Every idea this script creates is named with this prefix, so a run that died
#: partway through can be swept up by the next one.
PROBE_PREFIX = "QA content editor probe"

PROBE = {
    "title": f"{PROBE_PREFIX} {STAMP}",
    "description": (
        "Created by 05_content_editor.py to produce a draft to edit. "
        "Two short paragraphs about repairing a bicycle wheel is plenty."
    ),
    "content_type": "Blog Post",
    "platform": "Reddit",
    "goal": "Brand Awareness",
}

#: Appended to the draft in the editor. The timestamp makes it possible to tell
#: this run's edit from a previous run's when reading a draft by hand.
MARKER = f"[QA edit {STAMP}]"


# Confirmed by reading the page: the word count never updates. index.html
# registers a `counter` Quill module whose text-change handler writes the word
# count into <div id="counter">, but a registered module still has to be enabled
# on the instance through its `modules` option - and neither <quill-editor> tag
# passes one, so both get the component's default (toolbar only) and the handler
# is never bound. The div renders as an empty gap in the toolbar.
COUNTER_DEFECT = (
    "the counter module is registered but never enabled on the editor - no "
    "modules= on <quill-editor>, so its text-change handler is never bound"
)


class Checks:
    """Collects results so one failure does not hide the rest of the screen."""

    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []
        self.known: list[str] = []
        self.fixed: list[str] = []

    def that(self, label: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  ✅ {label}")
        else:
            self.failures.append(label)
            print(f"  ❌ {label}{f' - {detail}' if detail else ''}")
        return bool(condition)

    def equals(self, label: str, actual: object, expected: object) -> bool:
        return self.that(label, actual == expected, f"expected {expected!r}, got {actual!r}")

    def known_defect(self, label: str, condition: bool, note: str) -> bool:
        """A check whose failure is an already-diagnosed app bug.

        Reported, but not counted as a failure, so a real regression elsewhere
        still shows up. If it starts passing, that is called out too - a fixed
        bug should have its exemption removed rather than quietly kept.
        """
        if condition:
            self.fixed.append(label)
            print(f"  🎉 {label} - this known defect appears to be fixed; drop the exemption")
        else:
            self.known.append(label)
            print(f"  ⚠️  {label} - known defect: {note}")
        return bool(condition)

    def report(self) -> int:
        total = self.passed + len(self.failures)
        print(f"\n{self.passed}/{total} checks passed")
        for label in self.known:
            print(f"  known defect: {label}")
        for label in self.fixed:
            print(f"  now passing (remove exemption): {label}")
        for failure in self.failures:
            print(f"  failed: {failure}")
        return 0 if not self.failures else 1


def section(name: str) -> None:
    print(f"\n{name}")


def summarise(text: str, limit: int = 200) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + " ..."


def draft_the_probe(projects: CampaignProjectsPage, checks: Checks) -> str | None:
    """Add a throwaway idea and generate a draft for it. Returns its title.

    Only the probe is ticked: 🚀 Generate Content drafts every selected idea, and
    the selection survives a rerun, so a stale tick from an earlier session would
    quietly draft someone else's idea too.
    """
    projects.add_idea_manually(**PROBE)
    title = PROBE["title"]
    if not checks.that("the probe idea was added", title in projects.idea_titles()):
        return None

    projects.clear_selection()
    projects.idea(title).select_for_generation()
    if not checks.equals("only the probe is selected", projects.selected_count(), 1):
        return None

    print("  generating a draft - this calls the LLM and takes a while...")
    projects.generate_content()

    idea = projects.idea(title)
    if idea.generation_error().count():
        print("  ❌ Generation failed:")
        for message in projects.main.errors():
            print(f"     {message}")
        return None
    if not checks.that("the probe idea now has generated content", idea.has_generated_content()):
        return None

    projects.clear_selection()
    return title


def run(headed: bool, slow_mo: int, project_name: str | None,
        idea_title: str | None, keep: bool) -> int:
    checks = Checks()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=slow_mo)
        page = browser.new_page()
        page.set_default_timeout(config.DEFAULT_TIMEOUT)
        projects = CampaignProjectsPage(page)
        probe_title: str | None = None

        try:
            print(f"Signing in to {config.WEB_URL} as {config.USERNAME}")
            login = LoginPage(page).open()
            login.login()
            home = HomePage(page)
            home.expect_loaded()

            home.nav.refresh_projects()
            available = home.nav.project_names()
            if not available:
                print("\nNo campaign projects. Run scripts/02_project_from_story_idea.py first.")
                return 1
            target = project_name or available[0]
            if target not in available:
                print(f"\nNo project called {target!r}. Available: {available}")
                return 1

            projects.use_project(target)
            print(f"Project: {target}")
            if projects.current_screen() != "insights":
                print("The project is not on the insights screen - has its survey been completed?")
                return 1

            projects.close_idea_editor()

            # ---- reach a draft --------------------------------------------
            if idea_title:
                section(f"Using the existing idea {idea_title!r}")
                if idea_title not in projects.idea_titles():
                    print(f"  no such idea in this project. Found: {projects.idea_titles()}")
                    return 1
                if not projects.idea(idea_title).has_generated_content():
                    print("  that idea has no draft, so it has no 📝 Content Editor link.")
                    print("  Drop --idea to have this script draft its own throwaway idea.")
                    return 1
                editing = idea_title
            else:
                section("➕ Preparing a throwaway idea to edit")
                # A run that died mid-flight can leave probes behind.
                for stale in [t for t in projects.idea_titles() if t.startswith(PROBE_PREFIX)]:
                    print(f"  sweeping up a leftover probe idea: {stale}")
                    projects.idea(stale).edit().delete()

                probe_title = draft_the_probe(projects, checks)
                if probe_title is None:
                    return checks.report() or 1
                editing = probe_title

            idea = projects.idea(editing)
            before = summarise(idea.details.inner_text(), 300)
            print(f"  draft on the card: {before}")

            # ---- open the editor ------------------------------------------
            section("📝 Content Editor")
            checks.that("the link is on the idea card", idea.open_content_editor().count() == 1)

            editor = ContentEditorPage.open_from(idea)
            editor.wait_until_item_loaded()
            editor.wait_for_draft()
            checks.that("the editor opened in its own tab", editor.page != page)
            # Not a defect, but worth stating: the tour is unconditional, so
            # every visit starts behind it. ContentEditorPage dismisses it.
            checks.that("the guided tour was up on open, and was dismissed", editor.tour_seen)

            loaded = editor.text()
            checks.that(f"the Content Editor pane holds the draft ({len(loaded)} chars)",
                        bool(loaded))
            checks.equals("the Project dropdown shows the project",
                          editor.selected_project(), target)
            checks.equals("the Item dropdown shows the idea", editor.selected_item(), editing)
            # These two come from the item's single history row, so they are a
            # check on that lookup rather than on anything the user picked.
            checks.that(f"the Channel auto-selected ({editor.selected_channel()})",
                        editor.selected_channel() != "None")
            checks.that(f"the LLM auto-selected ({editor.selected_llm()})",
                        editor.selected_llm() != "None")
            print(f"  draft in the editor: {summarise(loaded)}")

            # ---- edit and save --------------------------------------------
            section("✏️ Editing and saving")
            editor.append_text(f"\n{MARKER}")
            checks.that("the typed marker is in the pane", MARKER in editor.text())
            count = (editor.word_count.inner_text() or "").strip()
            checks.known_defect(f"the word count updated (reads {count or 'empty'!r})",
                                count.isdigit(), COUNTER_DEFECT)

            editor.save_content()
            checks.that("the save was added to the History pane",
                        MARKER in editor.history.inner_text())

            # ---- prove it persisted ---------------------------------------
            section("🔄 Back in Streamlit")
            editor.close()
            projects.refresh_content()
            reloaded = projects.idea(editing)
            checks.that("the edit shows on the idea card after 🔄 Refresh Content",
                        MARKER in reloaded.details.inner_text())

            section("📝 Reopening the editor")
            reopened = ContentEditorPage.open_from(reloaded)
            reopened.wait_until_item_loaded()
            reopened.wait_for_draft()
            checks.that("the saved edit is in the reloaded draft", MARKER in reopened.text())
            reopened.close()

            return checks.report()

        finally:
            # Best effort: a failed run should still not leave a probe idea in
            # someone's project, but a cleanup failure must not mask the result.
            if probe_title and not keep:
                try:
                    projects.close_idea_editor()
                    if probe_title in projects.idea_titles():
                        projects.idea(probe_title).edit().delete()
                        print(f"\nDeleted the probe idea {probe_title!r}")
                        print("  (its query_history rows stay behind - the editor keeps "
                              "every save, and nothing in the UI deletes them)")
                except Exception as cleanup_error:  # noqa: BLE001 - diagnostics only
                    print(f"\nCould not delete the probe idea {probe_title!r}: {cleanup_error}")
            elif probe_title:
                print(f"\nLeaving the probe idea {probe_title!r} in place (--keep)")
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="show the browser")
    parser.add_argument(
        "--slow-mo", type=int, default=0, metavar="MS",
        help="pause between actions, to watch what it is doing",
    )
    parser.add_argument(
        "--project", default=None, metavar="NAME",
        help="which campaign project to work in (default: the first one)",
    )
    parser.add_argument(
        "--idea", default=None, metavar="TITLE",
        help="edit this already-drafted idea instead of creating a throwaway one, "
             "which spends no LLM call",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="do not delete the throwaway idea afterwards",
    )
    args = parser.parse_args()
    return run(args.headed, args.slow_mo, args.project, args.idea, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
