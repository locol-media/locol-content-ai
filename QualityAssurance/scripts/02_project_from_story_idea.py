"""02 - Turn the first saved story idea into a campaign project, and brainstorm its posts.

Second script in the sequence, covering Stage 3 and Stage 3b. It picks up where
`01` left off: the story ideas that script generated are reloaded from the
backend when the fourth survey page opens, so the *story* half costs no LLM
call. Generating the post ideas at the end does.

🚀 Create Project inside a story panel does three things at once - it creates
the project, puts it on the **Generated Story** question set, and pre-fills that
survey's two questions with a summary of the business survey and the story's own
angle. The script reports all three, completes the survey, then runs
🚀 Generate Strategic Campaigns to turn the story into the series of posts that
tell it. The first post it comes back with is always the introduction to the
series.

Three behaviours worth knowing, all of which this script works around rather
than papers over:

* **Project names are not unique.** Creating from a story names the project
  after the story, so running this twice leaves two identical entries. It skips
  creation when the name is already taken unless you pass `--force`.
* **The sidebar caches its project list** and creating from a story does not
  invalidate that cache, so the new project only appears after 🔄 Refresh.
* **Regenerating replaces every post idea in the project.** If the project
  already has ideas they are reported and left alone; `--regenerate` forces a
  fresh brainstorm over the top.

Usage, from the QualityAssurance folder:

    .venv/Scripts/python scripts/02_project_from_story_idea.py
    .venv/Scripts/python scripts/02_project_from_story_idea.py --headed --slow-mo 300
    .venv/Scripts/python scripts/02_project_from_story_idea.py --story-index 2
    .venv/Scripts/python scripts/02_project_from_story_idea.py --force
    .venv/Scripts/python scripts/02_project_from_story_idea.py --no-generate
    .venv/Scripts/python scripts/02_project_from_story_idea.py --regenerate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run as a plain script, so make the suite's own modules importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The app's headings are full of emoji and a Windows console defaults to cp1252,
# which cannot encode them - printing a story title would otherwise be the thing
# that fails, rather than anything to do with the project.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright  # noqa: E402

import config  # noqa: E402
from pages import BusinessSurveyPage, CampaignProjectsPage, HomePage, LoginPage  # noqa: E402

# The fourth survey page - 🎨 Hobbies & Interests - is the only place the story
# ideas are shown.
STORY_IDEAS_PAGE = 3

# The question set 🚀 Create Project always uses, and its two pre-filled fields.
QUESTION_SET = "Generated Story"
SUMMARY_FIELD = "q1"
SKILL_CONTENT_FIELD = "q2"


def summarise(text: str, limit: int = 400) -> str:
    """One-paragraph preview of a long pre-filled answer."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit].rstrip() + " ..."


def generate_post_ideas(projects: CampaignProjectsPage, regenerate: bool) -> int:
    """Stage 3b - turn the project survey into the series of posts.

    The project already sits on the insights screen with its survey answered,
    so this is the one remaining button. Existing ideas are left alone unless
    `regenerate` is set, because a fresh brainstorm replaces the whole set.
    """
    existing = projects.idea_titles()
    if existing and not regenerate:
        print(f"\nThe project already has {len(existing)} post idea(s) - not regenerating.")
        print("Pass --regenerate to replace them with a fresh brainstorm.")
    else:
        if existing:
            print(f"\nReplacing the {len(existing)} existing post idea(s)...")
        print("\nGenerating post ideas - this calls the LLM and takes a while...")
        projects.generate_campaigns()

        if projects.main.error().count():
            print("\n❌ Brainstorm failed:")
            for message in projects.main.errors():
                print(f"  {message}")
            return 1

    titles = projects.idea_titles()
    if not titles:
        print("\nNo post ideas were produced.")
        return 1

    print(f"\n🎯 {len(titles)} post idea(s) in this project:\n")
    for number, title in enumerate(titles, start=1):
        idea = projects.idea(title)
        lead = " (introduces the series)" if number == 1 else ""
        print(f"{number}. {title}{lead}")
        print(f"   {summarise(idea.description(), 300)}")
        print(f"   Content type: {idea.content_type()} | Platform: {idea.platform()}")
        print(f"   Goal: {summarise(idea.goal(), 160)}\n")

    return 0


def run(headed: bool, slow_mo: int, story_index: int, force: bool,
        generate: bool, regenerate: bool) -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=slow_mo)
        page = browser.new_page()
        page.set_default_timeout(config.DEFAULT_TIMEOUT)

        try:
            print(f"Signing in to {config.WEB_URL} as {config.USERNAME}")
            login = LoginPage(page).open()
            login.login()
            home = HomePage(page)
            home.expect_loaded()
            print(f"  signed in as {home.logged_in_user()}")

            survey = BusinessSurveyPage(page)
            home.nav.go_to_business_survey_page(STORY_IDEAS_PAGE)
            survey.wait_until_loaded()
            print(f"\nOn {survey.page_heading()}, where the saved story ideas live")

            titles = survey.story_idea_titles()
            if not titles:
                print(
                    "\nNo story ideas saved for this account. Run "
                    "scripts/01_business_survey_and_story_ideas.py first."
                )
                return 1

            print(f"  {len(titles)} story idea(s) available:")
            for number, title in enumerate(titles):
                marker = "->" if number == story_index else "  "
                print(f"  {marker} {number}. {title}")

            if story_index >= len(titles):
                print(f"\nNo story at index {story_index}; there are {len(titles)}.")
                return 1

            story_title = titles[story_index]
            panel = survey.open_story_idea(story_title)
            print(f"\nStory: {story_title}")
            for line in panel.inner_text().splitlines():
                if line.startswith(("Angle:", "Why relevant:", "Emotion:", "Source:")):
                    print(f"  {summarise(line, 300)}")

            # A project is named after its story, and names are not unique.
            projects = CampaignProjectsPage(page)
            home.nav.refresh_projects()
            existing = home.nav.project_names()
            if story_title in existing and not force:
                print(
                    f"\nA project called '{story_title}' already exists - skipping "
                    "creation. Pass --force to make a second one."
                )
            else:
                print("\nCreating the project...")
                survey.create_project_from_story(story_title)

                if survey.main.error().count():
                    print("Project creation failed:")
                    for message in survey.main.errors():
                        print(f"  {message}")
                    return 1

                # The rerun that follows the click re-renders the story panels
                # collapsed, so the confirmation is in the DOM but no longer
                # rendered - read it with alert_text() rather than inner_text().
                confirmation = survey.project_created_message()
                if not confirmation.count():
                    print("No confirmation message appeared - the project may not exist.")
                    return 1
                print(f"  {survey.main.alert_text(confirmation)}")

                # Creating from a story does not invalidate the sidebar's cached
                # project list, so the entry is not there until this runs.
                home.nav.refresh_projects()
                if story_title not in home.nav.project_names():
                    print("The project is not listed in the sidebar after a refresh.")
                    return 1
                print("  listed under 📁 Campaign Projects")

            print("\nOpening the project...")
            projects.use_project(story_title)
            print(f"  project id: {projects.project_id}")
            print(f"  landed on the {projects.current_screen()} screen")

            # The survey arrives already answered, which is what makes this
            # project ready for the brainstorm in 03.
            projects.edit_project_survey()
            print(f"  question set: {QUESTION_SET} - {projects.survey_progress()}")

            summary = projects.answer_text(SUMMARY_FIELD)
            skill_content = projects.answer_text(SKILL_CONTENT_FIELD)
            print(f"\n  Business Survey Summary ({len(summary)} chars, pre-filled):")
            print(f"    {summarise(summary)}")
            print(f"\n  Skill content for this project ({len(skill_content)} chars, pre-filled):")
            print(f"    {summarise(skill_content)}")

            if not summary or not skill_content:
                print("\nOne of the pre-filled answers is empty - check create_story_project.")
                return 1

            # Saves the survey and returns to the insights screen, which is
            # where the brainstorm button lives.
            projects.complete_discovery()
            print(f"\n✅ Project survey complete - on the {projects.current_screen()} screen")

            if not generate:
                print("Skipping the post-idea brainstorm (--no-generate)")
                return 0

            return generate_post_ideas(projects, regenerate)

        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="show the browser")
    parser.add_argument(
        "--slow-mo", type=int, default=0, metavar="MS",
        help="pause between actions, to watch what it is doing",
    )
    parser.add_argument(
        "--story-index", type=int, default=0, metavar="N",
        help="which saved story to use (default: 0, the first)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="create the project even if one with that name already exists",
    )
    parser.add_argument(
        "--no-generate", dest="generate", action="store_false",
        help="stop after the project survey, without brainstorming its posts",
    )
    parser.add_argument(
        "--regenerate", action="store_true",
        help="re-run the brainstorm, replacing any post ideas already in the project",
    )
    args = parser.parse_args()
    return run(
        args.headed, args.slow_mo, args.story_index, args.force,
        args.generate, args.regenerate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
