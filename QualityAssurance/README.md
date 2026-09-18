# QualityAssurance

Playwright page objects for the Locol Content AI UI, in Python — the same language as
the app they drive.

Two applications are covered:

| Page object | Screen | Route |
|---|---|---|
| `LoginPage` | Landing page: hero, 🔐 Login, 📝 Register | `/` |
| `HomePage` | "Welcome back" and the four stage cards | `/` |
| `Sidebar` | The global nav: Home, survey pages, projects, ideas, settings | *(every page)* |
| `BusinessSurveyPage` | Stage 2 survey and the Stage 2b story brainstorm | `/survey` |
| `CampaignProjectsPage` | Stage 3: create project, project survey, insights, post ideas, content generation | `/projectSurvey` |
| `IdeaCard` / `IdeaEditPanel` | One post idea and its ✏️ Edit panel | *(component)* |
| `FindYourVoicePage` | Stage 1 writing-style profiles | `/findYourVoice` |
| `ConfigManagerPage` | ⚙️ LLMs, Channels, Prompt Templates | `/configManager` |
| `ContentEditorPage` | Stage 4 Quill editor, served by BackEnd | `/www/index.html` |

## Running

```bash
cd QualityAssurance
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m playwright install chromium

# with Web on :8501 and BackEnd on :8000 already running
.venv/Scripts/python -m pytest -m smoke
.venv/Scripts/python -m pytest -m smoke --headed          # watch it
```

Point the suite somewhere else, or at another account, with environment
variables — `config.py` reads them all:

| Variable | Default |
|---|---|
| `QA_WEB_URL` | `http://localhost:8501` |
| `QA_API_URL` | `http://localhost:8000` |
| `QA_USERNAME` / `QA_PASSWORD` | `user01` / `user01` |
| `QA_TIMEOUT_MS` | `15000` |
| `QA_LLM_TIMEOUT_MS` | `240000` |

`tests/test_smoke.py` is a small read-only suite whose job is to fail when a UI
change breaks a locator. It writes nothing and calls no LLM. Tests that do
either should carry the `writes` or `llm` marker.

## Scripts

`scripts/` holds runnable walkthroughs built on the same page objects — useful
for seeding an account or watching a whole flow end to end. **The number prefix
is the running order**: each one leaves behind the state the next expects, and
they follow the app's own stages. `scripts/README.md` has the full sequence and
which numbers are still unwritten.

```bash
# create the account the rest of them run against (default: test02 / blahTest02)
.venv/Scripts/python scripts/register_user.py

# stage 2 and 2b: fill in the business survey as one persona, then generate story ideas
.venv/Scripts/python scripts/01_business_survey_and_story_ideas.py
.venv/Scripts/python scripts/01_business_survey_and_story_ideas.py --headed --slow-mo 300
.venv/Scripts/python scripts/01_business_survey_and_story_ideas.py --no-generate

# stage 4: draft an idea, edit it in the Content Editor, prove the save persists
.venv/Scripts/python scripts/05_content_editor.py
```

Unlike the smoke suite these **write to the account they sign in as**: there is
one business survey per account so it replaces what was there, and generating
story ideas discards the previous set and costs a real LLM call.

## Writing a test

```python
def test_first_idea_can_be_selected(logged_in):
    projects = CampaignProjectsPage(logged_in.page)
    projects.use_project("Restoring vintage bicycles")

    idea = projects.idea(projects.idea_titles()[0])
    idea.select_for_generation()

    assert projects.selected_count() == 1
```

## What the page objects know about Streamlit

These are the details that decide every locator, all verified against the
running app (Streamlit 1.49.1). They are the reason a generic Playwright
approach struggles here.

**A page load signs you out.** Authentication lives in `st.session_state`, which
a reload discards, so `page.goto("/survey")` lands on the landing page rather
than the survey. `Sidebar` is the only supported way to move between pages;
`open()` is for the landing page.

**`key=` is the hook.** A widget created with `key=x` gets a `st-key-x` class on
its container, and it is the only stable, human-chosen handle Streamlit gives
you. Both surveys pass each question's YAML field key straight through, so a
question is addressed as `st-key-business_name` rather than by its prose — and
`BusinessSurveyPage.PAGE_FIELDS` records those keys so a rename in
`Web/question-sets/` fails loudly rather than silently mismatching.

Per-record widgets follow the same rule with the record's id appended:

| Widget | Key |
|---|---|
| Project survey question | `<question_key>_<project_id>` |
| Idea: edit / checkbox | `edit_<idea_id>` / `select_<idea_id>` |
| Idea edit panel fields | `edit_title_<idea_id>`, `edit_desc_<idea_id>`, … |
| Config Manager row | `llm_name_<id>`, `channel_name_<id>`, `prompt_name_<id>` |
| Sidebar project / idea | `nav_project_<id>` / `nav_idea_<id>` |

`Sidebar.project_id(name)` and `IdeaCard.idea_id` recover those ids from the
DOM, so tests keep talking in names.

**A button with `help=` renders twice** — once inside a `stTooltipHoverTarget`,
once hidden alongside it. Every button locator filters on `:visible`, or strict
mode fails on the duplicate.

**Button labels sit in a nested `<p>`,** and role-name matching is a substring
match, so "Next ➡️" would also match a longer label containing it. Buttons are
matched with `p:text-is(...)`, which is exact.

**Widget labels become the field's `aria-label`** — including the escaped ` \*`
that marks a required question. That escape is the second reason to prefer keys
over labels; `input_by_label()` is there for the widgets that have no key.

**Waiting is explicit, and it has a trap.** Streamlit re-runs the whole script
on every interaction, and an interaction reaches the server over a websocket, so
the app takes a moment to flip out of idle. Checking whether it is busy *the
instant* you click sees the previous run's idle state and returns before
anything has re-rendered — the smoke suite caught exactly that. `wait_until_idle()`
therefore settles briefly (`SETTLE_MS`), then waits for Streamlit's own
`data-test-script-state` to read `notRunning` *and* for every container to drop
its `data-stale` flag. Each interaction helper calls it already.
`wait_for_llm()` is the same wait on the much longer AI timeout — keep
`QA_LLM_TIMEOUT_MS` above BackEnd's own `LOCOL_LLM_REQUEST_TIMEOUT` so a backend
timeout surfaces as the app's error message rather than as a Playwright one.

**`st.container(border=True)` has no testid of its own** in 1.49 — a saved voice
row is just a `stVerticalBlock`, so it is found as the innermost block holding
that voice's name.

## Notes on the app's own behaviour

Worth knowing before writing assertions, all documented in
[docs/how-to-use.md](../docs/how-to-use.md):

- **One business survey per account.** Saving replaces the previous answers.
- **Regenerating story ideas replaces the whole previous set.** 🗑️ Clear Story
  Ideas only hides them; the project page's 🗑️ Clear Strategic Response really
  deletes.
- **A project's question set is fixed at creation** and decides which questions
  its survey asks.
- **The first generated post idea is always the series introduction.**
- **📝 Content Editor appears on an idea only once it has a draft**, which is
  what "Unlocks later" on the Stage 4 home card means.
- **Content generation is capped at 25 ideas per batch**, and an open idea edit
  blocks sidebar navigation until it is saved or cancelled.
