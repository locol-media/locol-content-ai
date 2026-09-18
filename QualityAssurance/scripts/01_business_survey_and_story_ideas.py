"""01 - Sign in, fill in the whole business survey, and generate story ideas.

First script in the sequence: it covers Stage 2 and Stage 2b of the app's
workflow, and everything after it depends on the survey this leaves behind.
See scripts/README.md for the full running order.

Written from the point of view of one persona - a developer who builds a tool
that helps people tell their story on Reddit - so the survey reads like a real
account rather than filler. That matters: the story brainstorm reads the
Skills & Expertise and Hobbies & Interests pages most closely, and one-line
answers there produce bland stories.

This is a script, not a test. It **writes to the account it signs in as**:

* there is one business survey per account, so this replaces whatever was there;
* ✨ Generate Story Ideas discards any previously generated set and costs a real
  LLM call, which needs an LLM configured under ⚙️ Config Manager → 🤖 LLMs.

Usage, from the QualityAssurance folder:

    .venv/Scripts/python scripts/01_business_survey_and_story_ideas.py
    .venv/Scripts/python scripts/01_business_survey_and_story_ideas.py --headed --slow-mo 300
    .venv/Scripts/python scripts/01_business_survey_and_story_ideas.py --no-generate

Point it elsewhere with QA_WEB_URL / QA_USERNAME / QA_PASSWORD (see config.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run as a plain script, so make the suite's own modules importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The app's headings are full of emoji and a Windows console defaults to cp1252,
# which cannot encode them - printing a page title would otherwise be the thing
# that fails, rather than anything to do with the survey.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright  # noqa: E402

import config  # noqa: E402
from pages import BusinessSurveyPage, HomePage, LoginPage  # noqa: E402

# --- the persona ------------------------------------------------------------

INDUSTRY = "SaaS/Technology"
YEARS_EXPERIENCE = "10-20 years"

GOALS = [
    "Brand Awareness",
    "Thought Leadership",
    "Community Building",
    "Product Launches",
]

PAGE_1 = {
    "business_name": "Locol Content AI",
    "business_description": (
        "I build a tool that helps people turn what they already know - their work, "
        "their expertise, their hobbies - into Reddit posts that a community actually "
        "wants to read. It runs the whole cycle: a survey that draws out your "
        "background, an AI pass that proposes stories worth telling, a breakdown of "
        "each story into a series of posts, and a drafting step that writes them in "
        "your own voice. It never posts anything for you. The last judgement - is this "
        "genuinely useful to this subreddit - stays with the person."
    ),
    "target_audience": (
        "Founders, freelancers and small teams who know their subject cold but freeze "
        "at the blank page, and who have usually been burned once already by posting "
        "something promotional and watching it get downvoted into silence. Mostly "
        "one- to twenty-person companies without a marketing hire. They are not "
        "looking for more content; they want to be read by people who care about the "
        "thing they care about."
    ),
    "services": (
        "A guided business survey that captures your expertise and interests; "
        "AI-generated story ideas drawn from that background, each with an angle, a "
        "reason the audience should care, and suggested subreddits; campaign projects "
        "that break one story into a series of posts; saved voice profiles so drafts "
        "sound like you rather than like a chatbot; and a rich-text editor with the "
        "AI on call for rewrites."
    ),
    "unique_value": (
        "Most tools in this space help you advertise on Reddit. This one refuses to. "
        "It is built around the constraint that a community rewards people and "
        "punishes brands, so it starts from what you know rather than from what you "
        "sell, and it stops at a finished draft. Every account gets its own database "
        "and nothing is published anywhere without you pressing the button yourself."
    ),
}

PAGE_2 = {
    "audience_interests": (
        "How to write about your work without sounding like a press release; what "
        "actually gets upvoted in a technical subreddit; the etiquette of self-"
        "promotion and where the line really is; getting the first hundred users; "
        "war stories from people who shipped something and were honest about how it "
        "went."
    ),
    "current_content": (
        "Long, specific, first-person posts that admit what went wrong. A build log "
        "with real numbers outperforms a polished announcement every time. Anything "
        "that reads as a launch gets ignored; anything that reads as one person "
        "telling another what they learned gets replies and questions."
    ),
    "competitors": (
        "Generic AI writing assistants that will happily produce Reddit-shaped "
        "marketing copy, social schedulers with a Reddit checkbox bolted on, and - "
        "most of all - the agency retainer, or the founder simply deciding it is not "
        "worth the time and posting nothing at all."
    ),
    "influencers": (
        "r/SaaS, r/startups, r/Entrepreneur and the language-specific developer "
        "subreddits; Indie Hackers; Hacker News comment threads; people who write "
        "publicly about building in the open and about the mechanics of online "
        "communities rather than about growth hacking."
    ),
}

PAGE_3 = {
    "professional_expertise": (
        "Backend and full-stack engineering, and increasingly the practical end of "
        "applied AI: designing prompts that survive contact with real user input, "
        "keeping model output structured enough to store, and building the human "
        "review step that has to sit in front of anything a model writes. Alongside "
        "that, the unglamorous half - authentication, per-user data isolation, "
        "encrypting other people's API keys at rest, and capping what a runaway "
        "model call can cost."
    ),
    "technical_skills": (
        "Python and FastAPI on the backend, Streamlit for the app surface, "
        "TypeScript and Stencil with Quill for the editor, SQLite with one database "
        "per user, JWT with RS256 for sessions, Fernet for secrets at rest, Docker "
        "and Kubernetes for deployment, and Playwright for the browser tests. I run "
        "a static security scan over the tree rather than trusting that I remembered "
        "everything."
    ),
    "credentials": (
        "Nothing framed and hanging on a wall. Fifteen years of shipping software "
        "that other people depend on, a long list of production incidents I caused "
        "and then fixed, and the specific scar tissue of having handled other "
        "people's credentials and paid for the mistakes."
    ),
    "problems_solved": (
        "The blank page, mostly. People know something worth sharing and cannot see "
        "it, because to them it is just Tuesday. I have also solved the quieter "
        "problem underneath: how do you let a language model near your writing "
        "without it flattening your voice into the same LinkedIn mush as everyone "
        "else. And the operational one - how do you let each user bring their own "
        "model key without a compromised account running up somebody else's bill."
    ),
    "unique_approach": (
        "Work backwards from the audience, never from the product. The survey "
        "deliberately asks about hobbies before it asks about goals, because a "
        "restored bicycle or a decade of birdwatching is what makes a post read as a "
        "person. Then one story becomes a series rather than a single post, with the "
        "first instalment doing nothing but setting up the rest. A voice profile is "
        "written by hand and applied per project, so the style is a decision the "
        "person made rather than an average of the internet."
    ),
    "industry_mistakes": (
        "Treating a community as a distribution channel. Almost every failure I see "
        "starts there: the post is written to convert, the subreddit smells it "
        "instantly, and the account is done. The other big one is automating the "
        "last step - letting a tool publish for you - which removes the only "
        "judgement that actually matters. And in my own corner of the industry: "
        "shipping AI features with no human checkpoint, and storing users' provider "
        "keys in plain text because it was quicker."
    ),
}

PAGE_4 = {
    "personal_hobbies": (
        "I restore old mechanical keyboards - mostly 1980s boards that arrive full of "
        "somebody else's crumbs. Desoldering two hundred switches by hand is a strange "
        "kind of rest. I also read a lot of history, and I cook the same four dishes "
        "obsessively until they are right."
    ),
    "active_hobbies": (
        "Long walks with no destination, usually to think through a problem I have "
        "been staring at. Bouldering once a week, badly and cheerfully. I have a "
        "standing rule that any problem still unsolved after an hour gets taken "
        "outside, and it works far more often than it has any right to."
    ),
    "creative_hobbies": (
        "Writing, which is how I ended up building this. I have kept a private log "
        "for years of what I shipped and what broke, and the posts people respond to "
        "are almost always the entries I nearly deleted for being too honest. I also "
        "photograph the keyboards before and after, which has taught me more about "
        "narrative structure than anything else - the before shot is the hook."
    ),
    "learning_interests": (
        "How communities set and enforce their own norms, which is really what "
        "Reddit is. The history of manufacturing and why things used to be repairable. "
        "Typography. And the slow, unfashionable literature on how people actually "
        "change their minds, which turns out to be the whole game when you are "
        "writing for a sceptical audience."
    ),
    "hobby_communities": (
        "Deep in the mechanical keyboard subreddits and a couple of Discord servers "
        "where people post repair logs at two in the morning. That community taught "
        "me what good online writing looks like: someone photographs a broken "
        "controller board, explains what they tried, admits what they got wrong, and "
        "forty people show up to help. Nobody there is selling anything."
    ),
    "hobbies_and_business": (
        "Completely. The repair communities are the model the whole product is built "
        "on - show your work, admit the failures, and the community meets you "
        "halfway. Restoring keyboards also taught me to respect the thing I did not "
        "build: you cannot understand a board until you have traced why the last "
        "person did what they did. I try to write software the same way, and I try "
        "to write posts the same way."
    ),
    "audience_overlap": (
        "The repair habit, easily. My audience is mostly people who like to take "
        "things apart and understand them, and who are suspicious of anything that "
        "hides its workings - which is exactly the right instinct to bring to an AI "
        "writing tool. The other one is the private log: nearly every founder keeps "
        "some version of one and has never considered that it is already the raw "
        "material for a year of posts."
    ),
}


def fill(survey: BusinessSurveyPage, answers: dict[str, str]) -> None:
    for field_key, value in answers.items():
        survey.fill(field_key, value)
        print(f"    {field_key}")


def run(headed: bool, slow_mo: int, generate: bool) -> int:
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
            home.go_to_business_survey()
            survey.wait_until_loaded()

            print("\nPage 1 - 🏢 Basic Business Information")
            fill(survey, PAGE_1)
            survey.choose_industry(INDUSTRY)
            print(f"    industry -> {survey.selected_industry()}")
            survey.next_page()

            print("\nPage 2 - 🎯 Goals & Strategy")
            for goal in GOALS:
                survey.add_goal(goal)
            print(f"    business_goals -> {', '.join(survey.selected_goals())}")
            fill(survey, PAGE_2)
            survey.next_page()

            print("\nPage 3 - 💡 Skills & Expertise")
            fill(survey, PAGE_3)
            survey.main.select("years_experience", YEARS_EXPERIENCE)
            print(f"    years_experience -> {survey.main.selected_option('years_experience')}")
            survey.next_page()

            print("\nPage 4 - 🎨 Hobbies & Interests")
            fill(survey, PAGE_4)

            survey.expect_on_page(3)
            survey.save_survey()
            if survey.missing_required_error().count():
                print("\nSurvey refused to save:")
                print(f"  {survey.missing_required_error().first.inner_text()}")
                return 1
            print("\n✅ Business survey saved")

            if not generate:
                print("Skipping story generation (--no-generate)")
                return 0

            print("\nGenerating story ideas - this calls the LLM and takes a while...")
            survey.generate_story_ideas()

            if survey.main.error().count():
                print("\n❌ Story generation failed:")
                for message in survey.main.errors():
                    print(f"  {message}")
                return 1

            titles = survey.story_idea_titles()
            print(f"\n📖 {len(titles)} story idea(s) generated:\n")
            for number, title in enumerate(titles, start=1):
                panel = survey.open_story_idea(title)
                print(f"{number}. {title}")
                print(f"   {panel.inner_text().strip()}\n")

            return 0

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
        "--no-generate", dest="generate", action="store_false",
        help="fill in and save the survey, but do not call the LLM",
    )
    args = parser.parse_args()
    return run(args.headed, args.slow_mo, args.generate)


if __name__ == "__main__":
    raise SystemExit(main())
