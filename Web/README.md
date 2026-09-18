# Web

A [Streamlit](https://streamlit.io/) app that's the main entry point for Locol Content AI's guided content-creation workflow: account login, business survey, campaign brainstorming, and handoff to the [Content Editor](../FrontEnd) for drafting. It talks to [BackEnd](../BackEnd)'s FastAPI service for everything — accounts, config, and LLM invocation.

See the [root README](../README.md) for how this fits into the overall project.

## User journey

`src/main.py` sets up navigation with four sections once a user is authenticated:

1. **Home** — unauthenticated visitors see login/register forms (`POST /api/login-user`, `/api/register-user` on BackEnd); on successful login, `Web` mints its own session token locally — signing it with an RSA private key, then encrypting it to BackEnd's EC public key (see [Configuration](#configuration) and [docs/jwt.md](../docs/jwt.md)) — and shows a guided overview of the stages below.
2. **Find Your Voice** *(optional)* — write and save reusable "voice" profiles (writing-style prompts) that steer content generation; a project's chosen voice is layered onto the system prompt of every draft it generates. The Reddit-analysis half of the page is disabled — Reddit blocks the automated access it relied on — and returns behind `LOCOL_FIND_YOUR_VOICE_ENABLED`.
3. **Business Survey** — describe the business/expertise; the survey feeds an LLM that returns initial content/story ideas.
4. **Campaign Projects** — turn a story idea into a project: complete a strategic survey to sharpen the angle, then brainstorm specific content ideas per channel.
5. **Content Editor handoff** — once an idea has generated content, a link opens the [FrontEnd](../FrontEnd)-built Content Editor (served by BackEnd at `LOCOL_WWW_URL/www/index.html`) with the project/item/JWT passed via URL parameters.

A **Settings and Tools** section (Config Manager) lets a user manage which LLMs, channels, and prompt templates are available, and manage their saved voices.

## Module breakdown (`src/locol-lib/`)

- `apiClient.py` — shared `LOCOL_API_URL`/`LOCOL_WWW_URL` constants and `get_api_headers()` (attaches the JWT bearer token) used by every other module.
- `configManager.py` — Settings UI: CRUD tabs for LLM configs (API keys masked after the first save), channels, and prompt templates.
- `survey.py` — the Business Survey, driven by `question-sets/business_survey_questions.yaml` and `business_survey_page_configs.yaml`.
- `surveyRequired.py` — shared required/optional handling for both surveys: the `*` marker, the per-page legend, and the check that names unanswered required questions.
- `projectSurvey.py` — Campaign Projects: project creation/selection, the strategic survey (`question-sets/strategic_questions.yaml`), brainstorming, and the Content Editor handoff link.
- `findYourVoice.py` — saved-voice management: create a voice by hand, edit/clone/delete existing ones, and the disabled Reddit writing-style analyzer (`POST /api/findYourVoice`).
- `voices.py` — shared voice helpers: the session-cached voice list, and the `🎤 Voice` picker used by Campaign Projects, whose selection is stored per project via `GET/PUT /api/projects/{project_id}/voice`.
- `brainstorm_models.py`, `generate_items_models.py`, `models.py` — shared Pydantic request/response models for the brainstorm and content-generation endpoints.

## `question-sets/`

YAML files defining survey questions and page layouts (`business_survey_questions.yaml`, `strategic_questions.yaml`, and related page-config files). Keeping these as data rather than code lets survey copy/flow change without a rebuild — in Kubernetes they can be deployed as their own ConfigMap (see [docs/deploy-k8s.md](../docs/deploy-k8s.md)).

In any of these question sets, a question is mandatory when it carries `required: true` and optional otherwise. The flag is read twice — to mark the question with a `*` (and caption the page accordingly) and to block **Next ➡️** until the required answers are filled in — via the shared helpers in `locol-lib/surveyRequired.py`, so the Business Survey and the Project Survey behave identically. Only `business_survey_questions.yaml` marks anything required today; the project question sets are entirely optional as shipped.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `LOCOL_API_URL` | `http://localhost:$LOCOL_BACKEND_PORT` | Base URL for BackEnd API calls. The default follows `LOCOL_BACKEND_PORT` (`8000` unless set), so moving BackEnd off its default port needs no change here on a local run. |
| `LOCOL_WWW_URL` | `http://localhost:$LOCOL_BACKEND_PORT` | Base URL used to build the Content Editor handoff link. Same default as above. |
| `LOCOL_WEB_PORT` | `8501` | Port this app listens on in the container image. Running Streamlit by hand takes `--server.port` instead; `run-web-debug.ps1` reads this as the default for its `-WebPort`. |
| `LOCOL_JWT_KEYS_LOCATION` | `../keys` | Directory containing `private_key.pem`, used to sign session tokens at login, and `enc_public_key.pem`, used to encrypt them to `BackEnd/`. |
| `LOCOL_LLM_REQUEST_TIMEOUT` | `180` | Seconds to wait on an LLM-backed request (brainstorming, content generation, voice analysis). Plain CRUD calls keep their own short timeouts. |
| `LOCOL_FIND_YOUR_VOICE_ENABLED` | *(unset — analyzer off)* | Whether the Reddit writing-style analyzer is offered on the Find Your Voice page. Off because Reddit blocks the access it relies on; `BackEnd` reads the same variable and refuses the request independently, so set it on both services or neither. |

## Running locally

One-time setup (from the repo root, if not already done):

```powershell
./scripts/setup-local.ps1                       # macOS/Linux: ./scripts/setup-local.sh
```

Among other things this generates the two JWT key pairs this app signs and encrypts logins with, and creates `BackEnd/db/persistent_data.sqlite`, the shared accounts database behind login and registration. Without them, the register/login calls this app makes to BackEnd fail. It skips anything already set up, so it is safe to re-run. See [docs/deploy-local.md §4](../docs/deploy-local.md#4-one-time-setup) for what each step does.

Then, from `Web/`:

```bash
uv run streamlit run src/main.py --server.port=8501
```

The app is then served at `http://localhost:8501` and expects `BackEnd` to already be running (see [BackEnd/README.md](../BackEnd/README.md)). The repo-root `run-web-debug.ps1` starts both together.
