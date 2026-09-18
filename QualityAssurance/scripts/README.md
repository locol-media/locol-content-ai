# Scripts

Runnable walkthroughs built on the page objects in [`../pages`](../pages), for
seeding an account or watching a whole flow end to end.

**The number is the running order.** Each script leaves behind the state the
next one needs, so they are meant to be run in sequence against the same
account, and the prefix is there so that order survives being forgotten. They
follow the app's own stages — see [docs/how-to-use.md](../../docs/how-to-use.md).

| | Script | Stage | Leaves behind | Written |
|---|---|---|---|---|
| — | [`register_user.py`](register_user.py) | *before stage 1* | A new account that can sign in | ☑ |
| `00` | voices | 1 — Find Your Voice | Saved writing-style profiles, pickable on a project | ☐ |
| `01` | [`01_business_survey_and_story_ideas.py`](01_business_survey_and_story_ideas.py) | 2 and 2b | The account's business survey, and a set of story ideas | ☑ |
| `02` | [`02_project_from_story_idea.py`](02_project_from_story_idea.py) | 3 and 3b | A campaign project with its survey complete, and the series of post ideas | ☑ |
| `03` | [`03_idea_box.py`](03_idea_box.py) | 3b | Nothing — it works on its own throwaway idea and deletes it | ☑ |
| `04` | content generation | 3c | Drafts against the selected ideas | ☐ |
| `05` | [`05_content_editor.py`](05_content_editor.py) | 4 (and 3c for one idea) | Nothing — it drafts its own throwaway idea, edits it and deletes it | ☑ |

`register_user.py` has no number because it is not a link in the chain: it
creates the account the numbered scripts then run against, and consumes no
state of its own. Run it only when you need a fresh account.

`00` is optional and sits outside the chain: it only has to run before `04`, and
only if you want the drafts written in a saved voice rather than the house tone.

`05` needs a draft to edit, and a draft is `04`'s output — so rather than depend
on a script that does not exist yet, it generates one for a single throwaway
idea of its own. That does not make `04` redundant: a batch walkthrough of
Stage 3c — the selection rules, the voice picker, the 25-idea cap — is still
unwritten, which is why `04` keeps its row.

Numbers are reserved rather than only assigned as scripts are written, so a
later addition slots in without renumbering the ones already in use. When two
stages end up in one script, the number it displaced is left free for the same
reason — `02` grew to cover 3b, so `03` stays open rather than everything
shuffling up.

## Running

From the `QualityAssurance` folder, with Web on :8501 and BackEnd on :8000:

```bash
.venv/Scripts/python scripts/register_user.py                                  # test02 / blahTest02
.venv/Scripts/python scripts/register_user.py --username test03 --password blahTest03
.venv/Scripts/python scripts/register_user.py --email qa+test02@example.com

.venv/Scripts/python scripts/01_business_survey_and_story_ideas.py             # Linux/macOS: .venv/bin/python
.venv/Scripts/python scripts/01_business_survey_and_story_ideas.py --headed --slow-mo 300
.venv/Scripts/python scripts/01_business_survey_and_story_ideas.py --no-generate

.venv/Scripts/python scripts/02_project_from_story_idea.py
.venv/Scripts/python scripts/02_project_from_story_idea.py --story-index 2   # a different story
.venv/Scripts/python scripts/02_project_from_story_idea.py --force           # allow a duplicate
.venv/Scripts/python scripts/02_project_from_story_idea.py --no-generate     # stop before the brainstorm
.venv/Scripts/python scripts/02_project_from_story_idea.py --regenerate      # replace existing post ideas

.venv/Scripts/python scripts/03_idea_box.py
.venv/Scripts/python scripts/03_idea_box.py --project "My story"
.venv/Scripts/python scripts/03_idea_box.py --no-generate                    # skip the brainstorm call
.venv/Scripts/python scripts/03_idea_box.py --keep                           # leave the probe idea behind

.venv/Scripts/python scripts/05_content_editor.py
.venv/Scripts/python scripts/05_content_editor.py --project "My story"
.venv/Scripts/python scripts/05_content_editor.py --idea "An already-drafted idea"  # no LLM call
.venv/Scripts/python scripts/05_content_editor.py --keep                     # leave the probe idea behind
```

`register_user.py` runs against the login page rather than an account, so
`QA_USERNAME` / `QA_PASSWORD` do not apply to it — pass `--username` and
`--password` instead. It verifies the new account by signing in as it, rather
than trusting the form's confirmation message; that check is what caught Web
reporting a registration the backend had refused as a success. BackEnd also
rate-limits registration to **five attempts an hour**, so the script probes for
an existing account before spending one.

`05` is the only script that leaves Streamlit: it drives the Quill editor
BackEnd serves at `/www/index.html`, then comes back to the project page to
confirm the edit arrived. It has no `--no-generate`, because a draft is its
precondition rather than its finale — it always spends one LLM call unless
`--idea` points it at an idea that is already drafted. Two things it found and
now documents: the editor starts a guided tour on **every** load whose overlay
swallows clicks until dismissed (`ContentEditorPage` handles this, so tests do
not have to), and the toolbar's word count never updates — reported as a known
defect, not a failure. On a project with a dozen ideas the insights screen can
take longer than the default 15s to settle; `QA_TIMEOUT_MS=60000` covers it.

`03` is the odd one out: rather than advancing the workflow it checks one post
idea's controls and prints a pass/fail line for each, so it can be run at any
point once a project has ideas. It is also the only script that reports **known
defects** — checks whose failure is an already-diagnosed app bug, listed
separately so they neither hide a real regression nor turn the run red for
something already understood. If a known defect starts passing, the script says
so, and the exemption should be removed.

Each script takes `--headed` and `--slow-mo` so you can watch it, and every one
that calls an LLM takes `--no-generate` to stop short of the AI call. `02`
reuses the story ideas `01` saved rather than regenerating them, so its only AI
call is the post-idea brainstorm at the end.

`QA_WEB_URL`, `QA_USERNAME` and `QA_PASSWORD` choose the target — see
[`../config.py`](../config.py).

## These write to the account

Unlike [`../tests`](../tests), which is read-only, these scripts change data:

- there is **one business survey per account**, so `01` replaces whatever was
  there;
- **generating story ideas discards the previous set** and costs a real LLM
  call, which needs an LLM configured under ⚙️ Config Manager → 🤖 LLMs.

Run them against a test account, not one whose work you care about.

## Adding one

Copy the shape of `01`: persona data as module-level constants at the top, a
`run()` that drives the page objects and prints what it did, and an `argparse`
`main()`. Give it the next free number, tick its row above, and keep it
idempotent — a script that has already run once will meet a half-filled account
the second time, which is how the multiselect bug in `StreamlitRegion` was
found.
