"""03 - Exercise every control on a single post idea card.

The "idea box" is the unit the whole of Stage 3 revolves around: a header row
(title, ✏️ Edit, an optional 📝 Content Editor link, and the Generate Content
checkbox), a View Details panel, and behind Edit a five-field form plus the
💡 Brainstorm Content Snippet section. This script walks all of it and prints a
pass/fail line per check, rather than stopping at the first problem - the point
is a report on the whole card.

It works on **its own throwaway idea**, added through ➕ Add Campaign Idea
Manually and deleted at the end, so the ideas `02` generated are never touched.
Pass `--keep` to leave it behind for inspection.

What it deliberately does not touch:

* **🗑️ Clear Strategic Response**, which deletes every idea in the project.
* **🚀 Generate Content**, which belongs to `04` - so the card under test never
  gains generated content, and the 📝 Content Editor link is checked for its
  *absence* here.

Usage, from the QualityAssurance folder:

    .venv/Scripts/python scripts/03_idea_box.py
    .venv/Scripts/python scripts/03_idea_box.py --headed --slow-mo 300
    .venv/Scripts/python scripts/03_idea_box.py --project "My story"
    .venv/Scripts/python scripts/03_idea_box.py --no-generate   # skip the brainstorm
    .venv/Scripts/python scripts/03_idea_box.py --keep          # do not delete the test idea
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
from pages import CampaignProjectsPage, HomePage, LoginPage  # noqa: E402
from pages.campaign_projects_page import NO_VOICE  # noqa: E402

STAMP = datetime.now().strftime("%H:%M:%S")

#: Every idea this script creates is named with this prefix, so a run that died
#: partway through can be swept up by the next one.
PROBE_PREFIX = "QA idea box probe"

ORIGINAL = {
    "title": f"{PROBE_PREFIX} {STAMP}",
    "description": "Created by 03_idea_box.py to exercise the card's controls.",
    "content_type": "Blog Post",
    "platform": "Reddit",
    "goal": "Brand Awareness",
}

EDITED = {
    "title": f"{PROBE_PREFIX} {STAMP} (edited)",
    "description": "Edited by the same script, to prove Save Changes persists.",
    "content_type": "Case Study",
    "platform": "Reddit (edited)",
    "goal": "Thought Leadership",
}

BRAINSTORM_PROMPT = "Suggest three headline variations for this campaign idea."

# Confirmed by hand against the running app, on generated and manually added
# ideas alike: the Generate Content checkbox is one-way. Once ticked it cannot
# be unticked and the selected count only grows; 🗑️ Clear Selection is the only
# way back. The cause is in projectSurvey.py's display_brainstorm_ideas_table,
# where the checkbox is given both a key and `value=idea_id in selected_ideas`.
# The value argument is recomputed from a set the same run then mutates, so the
# user's False is overwritten by the recalculated True on the next rerun.
UNTICK_DEFECT = (
    "the checkbox is passed both key= and value=, so the recomputed default "
    "overwrites the user's choice on the next rerun"
)


class Checks:
    """Collects results so one failure does not hide the rest of the card."""

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
        return condition

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
        return condition

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


def run(headed: bool, slow_mo: int, project_name: str | None,
        generate: bool, keep: bool) -> int:
    checks = Checks()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=slow_mo)
        page = browser.new_page()
        page.set_default_timeout(config.DEFAULT_TIMEOUT)
        created_title: str | None = None
        projects = CampaignProjectsPage(page)

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

            # A run that died mid-edit can leave a probe behind, so clear any
            # out before counting - otherwise they accumulate in the project.
            projects.close_idea_editor()
            for stale in [t for t in projects.idea_titles() if t.startswith(PROBE_PREFIX)]:
                print(f"  sweeping up a leftover probe idea: {stale}")
                projects.idea(stale).edit().delete()

            baseline = projects.idea_titles()
            print(f"  {len(baseline)} existing idea(s), which this script leaves alone")

            # ---- create ---------------------------------------------------
            section("➕ Add Campaign Idea Manually")
            projects.add_idea_manually(**ORIGINAL)
            created_title = ORIGINAL["title"]
            titles = projects.idea_titles()
            checks.that("the new idea appears in the list", created_title in titles)
            checks.equals("the list grew by exactly one", len(titles), len(baseline) + 1)

            idea = projects.idea(created_title)

            # ---- view details ---------------------------------------------
            section("View Details")
            checks.equals("description", idea.description(), ORIGINAL["description"])
            checks.equals("content type", idea.content_type(), ORIGINAL["content_type"])
            checks.equals("platform", idea.platform(), ORIGINAL["platform"])
            checks.equals("goal", idea.goal(), ORIGINAL["goal"])
            checks.that(
                "no 📝 Content Editor link, because there is no draft yet",
                idea.open_content_editor().count() == 0,
            )
            checks.that(
                "no generated content section",
                not idea.has_generated_content(),
            )

            # ---- selection checkbox ---------------------------------------
            section("Generate Content checkbox")
            before = projects.selected_count()
            idea.select_for_generation(True)
            checks.that("ticking it reports the idea as selected", idea.is_selected())
            checks.equals("the selection count goes up by one",
                          projects.selected_count(), before + 1)
            idea.select_for_generation(False)
            checks.known_defect(
                "unticking it clears the selection",
                not idea.is_selected(),
                UNTICK_DEFECT,
            )
            checks.known_defect(
                "the selection count returns to where it started",
                projects.selected_count() == before,
                "the count only ever grows, for the same reason",
            )
            # 🗑️ Clear Selection is the only way back, so the card is left as
            # this script found it.
            projects.clear_selection()
            checks.that("🗑️ Clear Selection unticks everything",
                        not idea.is_selected())
            checks.equals("and the count is back to zero",
                          projects.selected_count(), 0)

            # ---- edit panel: opening --------------------------------------
            section("✏️ Edit - opening the panel")
            panel = idea.edit()
            checks.equals("every other idea is hidden while editing",
                          len(projects.idea_titles()), 0)
            checks.equals("the title field is pre-filled", panel.title(), ORIGINAL["title"])

            section("✏️ Edit - navigation is blocked while editing")
            home.nav.open_project(target)
            checks.that(
                "the sidebar refuses to navigate and says why",
                home.nav.edit_in_progress_warning().count() > 0,
            )
            checks.equals("and the panel is still open", panel.title(), ORIGINAL["title"])

            # ---- edit panel: cancel ---------------------------------------
            section("❌ Cancel discards changes")
            panel.set_title("this title should never be saved")
            panel.cancel()
            titles = projects.idea_titles()
            checks.that("the original title survives a cancel", created_title in titles)
            checks.that("the discarded title was not saved",
                        "this title should never be saved" not in titles)

            # ---- edit panel: save -----------------------------------------
            section("💾 Save Changes writes all five fields")
            panel = projects.idea(created_title).edit()
            panel.set_title(EDITED["title"])
            panel.set_description(EDITED["description"])
            panel.set_content_type(EDITED["content_type"])
            panel.set_platform(EDITED["platform"])
            panel.set_goal(EDITED["goal"])
            panel.save()
            created_title = EDITED["title"]

            edited = projects.idea(created_title)
            checks.that("the card shows the new title", edited.exists())
            checks.equals("description", edited.description(), EDITED["description"])
            checks.equals("content type", edited.content_type(), EDITED["content_type"])
            checks.equals("platform", edited.platform(), EDITED["platform"])
            checks.equals("goal", edited.goal(), EDITED["goal"])

            section("...and the edit survives leaving the project")
            home.nav.go_home()
            projects.use_project(target)
            checks.that("the edited idea is still there after a round trip",
                        created_title in projects.idea_titles())

            # ---- brainstorm -----------------------------------------------
            section("💡 Brainstorm Content Snippet")
            panel = projects.idea(created_title).edit()
            checks.equals("the 🎤 Voice picker defaults to no voice",
                          projects.main.selected_option(f"brainstorm_voice_{panel.idea_id}"),
                          NO_VOICE)

            panel.brainstorm_button().click()
            projects.wait_until_idle()
            checks.that("an empty prompt is refused",
                        panel.empty_prompt_warning().count() > 0)

            if generate:
                print(f"  running the brainstorm - this calls the LLM: {BRAINSTORM_PROMPT!r}")
                panel.brainstorm(BRAINSTORM_PROMPT)
                if projects.main.error().count():
                    checks.that("the brainstorm succeeded", False,
                                "; ".join(projects.main.errors()))
                else:
                    response = panel.response()
                    checks.that("a response comes back", bool(response.strip()),
                                f"got {response!r}")

                    # Previous Content Snippets is an st.dataframe, drawn on a
                    # canvas - readable through its accessibility rows, which
                    # render a beat after Streamlit goes idle.
                    panel.wait_for_snippets(1)
                    checks.that("the run is kept in Previous Content Snippets",
                                panel.snippet_count() >= 1,
                                f"grid holds {panel.snippet_count()} row(s)")
                    if panel.snippet_count():
                        stamp, prompt, snippet = panel.snippet_row(0)
                        checks.equals("the stored prompt is the one just sent",
                                      prompt, BRAINSTORM_PROMPT)
                        checks.that("the stored snippet has content", bool(snippet))
                        checks.that("and it is timestamped", bool(stamp))

                        panel.open_snippet(0)
                        checks.equals("clicking the row selects it",
                                      panel.selected_snippet_row(), 0)

                    print(f"\n  response ({len(response)} chars):")
                    for line in response.splitlines()[:6]:
                        print(f"    {line}")
            else:
                print("  skipping the brainstorm itself (--no-generate)")

            panel.cancel()

            # ---- shared voice selection -----------------------------------
            section("🎤 Voice is one selection shared by both pickers")
            checks.equals("the Generate Content picker agrees with the panel's",
                          projects.selected_voice(), NO_VOICE)

            saved_voices = [v for v in projects.voice_options() if v != NO_VOICE]
            if not saved_voices:
                print("  no saved voices on this account, so there is nothing to pick "
                      "- create one under 🎤 Find your voice to cover this")
            else:
                voice = saved_voices[0]
                print(f"  picking a saved voice: {voice!r}")
                projects.choose_voice(voice)
                checks.equals("choosing a voice sticks rather than snapping back",
                              projects.selected_voice(), voice)

                home.nav.go_home()
                projects.use_project(target)
                checks.equals("and it is still selected after a round trip",
                              projects.selected_voice(), voice)

                panel = projects.idea(created_title).edit()
                checks.equals("the panel's picker shows the same voice",
                              panel.selected_voice(), voice)

                panel.choose_voice(NO_VOICE)
                checks.equals("clearing it in the panel sticks too",
                              panel.selected_voice(), NO_VOICE)
                panel.cancel()
                checks.equals("and clears the Generate Content picker with it",
                              projects.selected_voice(), NO_VOICE)

            # ---- delete ---------------------------------------------------
            if keep:
                print(f"\nLeaving the test idea in place (--keep): {created_title}")
                created_title = None
            else:
                section("🗑️ Delete")
                projects.idea(created_title).edit().delete()
                remaining = projects.idea_titles()
                checks.that("the idea is gone from the list", created_title not in remaining)
                checks.equals("the list is back to its original size",
                              len(remaining), len(baseline))

                home.nav.go_home()
                projects.use_project(target)
                checks.that("and it stays gone after a round trip",
                            created_title not in projects.idea_titles())
                created_title = None

            return checks.report()

        finally:
            # Never leave a probe idea behind because something failed midway.
            if created_title and not keep:
                try:
                    print(f"\nCleaning up the test idea: {created_title}")
                    # A failure mid-edit leaves the panel open, and while it is
                    # open there is no idea list to find the card in.
                    projects.close_idea_editor()
                    projects.idea(created_title).edit().delete()
                    print("  removed")
                except Exception as cleanup_error:  # pragma: no cover - best effort
                    print(f"  could not remove it: {cleanup_error}")
                    print(f"  delete {created_title!r} by hand, or re-run this script -")
                    print("  it sweeps up leftover probes before it starts.")
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="show the browser")
    parser.add_argument(
        "--slow-mo", type=int, default=0, metavar="MS",
        help="pause between actions, to watch what it is doing",
    )
    parser.add_argument(
        "--project", metavar="NAME",
        help="which project to work in (default: the first in the sidebar)",
    )
    parser.add_argument(
        "--no-generate", dest="generate", action="store_false",
        help="exercise the brainstorm panel without making the AI call",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="leave the test idea in the project instead of deleting it",
    )
    args = parser.parse_args()
    return run(args.headed, args.slow_mo, args.project, args.generate, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
