# BackEnd

The FastAPI service that powers Locol Content AI. It's the single source of truth for user accounts, per-user data, LLM configuration, and content generation — both the [Web](../Web) (Streamlit) app and the [FrontEnd](../FrontEnd) Content Editor talk to it as their API backend.

See the [root README](../README.md) for how this fits into the overall project, and [docs/deploy-k8s.md](../docs/deploy-k8s.md) for Kubernetes deployment.

## Architecture

Source lives in `src/`, grouped by concern:

**Auth / accounts**
- `jwt_auth.py` — decrypts session tokens with the EC private key, then verifies the RS256 signature inside with the RSA public key (it holds neither the signing key nor the encryption public key — those live with `Web/`), and exposes FastAPI dependencies for extracting the authenticated user. See [docs/jwt.md](../docs/jwt.md).
- `user_management.py` — registration/login against the shared `users` table (bcrypt password hashing). See [docs/password-hashing.md](../docs/password-hashing.md) for a plain-English walkthrough of the hashing and the known gaps.
- `user_models.py` — request/response models for register/login.

**Per-user data & config**
- `db_manager.py` — manages one SQLite database per user (`db/users/<user_id>.sqlite`), including path sanitization, an async-safe "current user" context, and first-time table creation/seeding.
- `config_manager.py` — CRUD for a user's LLM/Channel/Prompt configs. LLM API keys are encrypted at rest and only ever returned to clients masked (last 4 characters visible).
- `db_crypto.py` — Fernet encryption helpers used to store LLM API keys at rest. A value that won't decrypt is never assumed to be plaintext and never written back: `decrypt_value()` raises `UndecryptableValue`, and `decrypt_or_none()` returns `None` for callers that are only scanning for a marker prefix.
- `load_channels.py`, `load_llms.py`, `load_prompts.py` — sync the default YAML config (see below) into a user's tables.
- `bifrost_manager.py` — gives the LLM row named **`Locol AI Default`** a per-user [Bifrost](https://docs.getbifrost.ai/) virtual key, creating the customer and key if they don't exist and reusing them if they do, then repoints the row at the gateway (`APIstyle: openai`, `APIurl: <bifrost>/v1`, `APIkey:` the virtual key). Runs on registration and again from `db_manager.ensure_user_defaults_seeded()`, so it self-heals; once the row holds a key it costs one `SELECT`. Off unless `LOCOL_BIFROST_URL` is set; failures are logged (with a backoff) and never block a request. `load_llms.py` skips resyncing rows holding a virtual key so a config reload can't revert the routing.

  > The marker name couples the code to `config/default/llms/llm.yaml` — change one and you must change the other, or provisioning silently finds nothing.
- `persist_data.py`, `persist_history.py` — generic dropdown/table persistence and LLM-invocation history.
- `buttons_handler.py` — thin wrappers used by the front-end dropdown lists.
- `business_models.py` / `business_survey.py`, `voice_manager.py`, `story_creation_models.py` / `story_ideas.py`, `project_brainstorming_ideas.py`, `generate_items_models.py`, `models.py` — models and persistence for the business survey, saved "voice" presets (including which voice a project generates in, and layering that voice onto an agent's system prompt), story ideas, and project/brainstorm data.
- `quill_delta.py`, `quill_op.py`, `quill_html_to_delta.py` — convert LLM HTML output to/from the Quill editor's Delta format, so generated content drops straight into the Content Editor.

**LLM invocation**
- `llm.py` — the `LLM` class wrapping `pydantic-ai`: loads a config row (decrypting its API key), sets the right provider env var (`OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY`) based on the config's `APIstyle`, and invokes the model with retry/backoff on HTTP 429s.
- `prompt.py` — builds prompt strings from templates.

**Content-generation agents**
- `rag_run.py` — the primary content-generation agent (`invoke()`/`save_content()`), recording results to history.
- `brainstorm_agent.py`, `brainstorm_content_snippet.py` — brainstorming ideas and content snippets for a campaign.
- `story_creation_agent.py` — turns business-survey answers into personal story ideas.
- `find_your_voice.py` — **disabled by default.** It derived a reusable writing-style prompt for a Reddit user without reading Reddit: it asked the Serper search API for Google results matching `site:reddit.com "u/<username>"` and analyzed the result *snippets*. Reddit now blocks the automated access that pipeline depends on, so `find_your_voice_invoke()` returns a plain "unavailable" message unless `LOCOL_FIND_YOUR_VOICE_ENABLED` is set. The search-and-analyze code is left intact behind that flag. Voices are otherwise written by hand in the Web UI.
- `generate_project_items.py` — merges selected brainstormed ideas into a project's content items.

FastAPI wiring lives in `main.py`: CORS, `slowapi` rate limiting (5/hour registration, 10/minute login), static file mounting of `www/` (the built [FrontEnd](../FrontEnd) Content Editor, served at `/www/index.html`), and an `ensure_user_context` dependency that nearly every route uses to authenticate the caller and set up their per-user database context.

> **Security note:** four endpoints that used to exist here were removed because they were unauthenticated. Three were admin-style and could delete/create arbitrary user data: `/api/recreate-users-table`, `/api/init-user-database/{user_id}` and `/api/set-current-user/{user_id}`. `init_user_database` and `set_current_user` are still used internally (during registration and JWT authentication respectively), just not exposed as routes; `recreate_users_table` has been deleted outright, since reissuing user ids orphans the `db/users/<user_id>.sqlite` files named after them.
>
> The fourth, `/api/current-user`, reported session state with no token. It was deleted rather than authenticated: giving it `ensure_user_context` would have made it echo back the `user_id` from the token the caller had just presented, which is no information they did not already hold. Nothing called it. [`tests/test_route_auth.py`](tests/test_route_auth.py) now asserts that every `/api/` route carries the dependency, with an explicit two-entry allowlist for register and login, so a future route added without it fails the suite.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `LOCOL_BACKEND_PORT` | `8000` | Port this service listens on when started with `python src/main.py`. `Web` reads the same variable to build its default `LOCOL_API_URL`, so a local run only needs it set once. Launching via the uvicorn CLI instead (as `run-web-debug.ps1` does) uses `--port`. |
| `LOCOL_USER_DB_PORT` | `8081` | Port `start_user_db.sh` serves a single user's database on. |
| `LOCOL_CONFIG_LOCATION` | `./config` | Root directory for default YAML config (channels/LLMs/prompt templates). |
| `LOCOL_JWT_KEYS_LOCATION` | `../keys` | Directory containing `enc_private_key.pem`, used to decrypt session tokens, and `public_key.pem`, used to verify the signature inside them. Both issued by `Web/`. |
| `LOCOL_DB_ENCRYPTION_KEY_LOCATION` | `../keys` | Directory containing `db_encryption.key`, used to encrypt LLM API keys at rest. |
| `LOCOL_FIND_YOUR_VOICE_ENABLED` | *(unset — analyzer off)* | Re-enables the Reddit writing-style analyzer in `find_your_voice.py`, which is off because Reddit blocks the access it relies on. `Web` reads the same variable to decide whether to offer the form, so set it on both services or neither. |
| `SERPER_API_KEY` | *(unset — feature off)* | Google-search API key used by `find_your_voice.py`. Only read when the analyzer is enabled *and* invoked; every other endpoint works without it. |
| `LOCOL_BIFROST_ENABLED` | *(unset — falls back to `LOCOL_BIFROST_URL`)* | Whether users are routed through Bifrost. Unset means on if `LOCOL_BIFROST_URL` is set, which keeps older deployments and local runs behaving as before; `false` turns it off even with a URL set. Turning it off only stops new provisioning — users already provisioned keep routing through the gateway. |
| `LOCOL_BIFROST_URL` | *(empty — feature off)* | Base URL of a [Bifrost](https://docs.getbifrost.ai/) LLM gateway; required whenever the flag above is on. Registration then provisions a Bifrost customer and virtual key per user and points their default LLM at the gateway — see `bifrost_manager.py`. |
| `LOCOL_BIFROST_ADMIN_TOKEN` | unset | Bearer token for Bifrost's governance API. Only sent if set; Bifrost's admin API is unauthenticated by default. |
| `LOCOL_BIFROST_DEFAULT_MODEL` | *(unset — falls back to the seeded row's own `model`)* | Model a provisioned LLM is pointed at, in Bifrost's `provider/model` form. The user's virtual key is scoped to exactly this provider and model, so the prefix is what decides which upstream serves a call; with neither this nor a `model:` on the row, provisioning is skipped. Changing it only affects users who register afterwards. |
| `LOCOL_BIFROST_BUDGET_MAX_LIMIT` | *(empty — uncapped)* | Spend cap in **dollars** put on each virtual key at creation. |
| `LOCOL_BIFROST_BUDGET_RESET_DURATION` | `1M` | Reset period for that cap — `30s`, `5m`, `1h`, `1d`, `1w`, `1M` or `1Q`. |
| `LOCOL_BIFROST_TIMEOUT` | `5` | Seconds to wait on each governance call during registration. |
| `LOCOL_BIFROST_RETRY_INTERVAL` | `300` | Seconds a user is left alone after a failed provisioning attempt, so a Bifrost outage doesn't add a timed-out call to every request. |
| `LOCOL_CORS_ALLOW_ORIGINS` | *(empty — no origin allowed)* | Comma-separated origins allowed to call the API from a browser. Empty leaves the CORS middleware inert, which is the intended state: the Content Editor is served from `/www` by this same app, and `Web` calls the API server-side where CORS never applies. Only set it if `LOCOL_WWW_URL` and `LOCOL_API_URL` point at different hosts — see [docs/security-management.md §7](../docs/security-management.md#7-the-network-edge) first, since the empty allowlist is one of three things standing in for a CSRF token. |
| `DEBUG` | unset | Truthy values (`true`/`1`/`yes`) enable verbose LLM/agent logging. |

`config/default/` holds the seed data loaded into every new user's database on first registration:
- `channels/channels.yaml` — distribution channels content can target (LinkedIn, Bluesky, Reddit, etc.)
- `llms/llm.yaml` — available LLM configs (id, name, `APIstyle`, API key, optional URL/model). It ships with a placeholder key. **Prefer setting your real key in the app** (register, then ⚙️ Config Manager → 🤖 LLMs → `Locol AI Default`), where it is encrypted at rest and belongs to one account — this file is tracked by git and seeds every user with the same key. See [docs/deploy-local.md §4.3](../docs/deploy-local.md#43-the-llm-provider-key).
- `promptTemplates/*.yaml` — prompt templates used for content generation.

## Running locally

One-time setup (from the repo root, if not already done):

```powershell
./scripts/setup-local.ps1                       # macOS/Linux: ./scripts/setup-local.sh
```

This generates the JWT key pairs and database encryption key, creates the shared accounts database, syncs dependencies, and prompts for an LLM provider key. It skips anything already set up, so it is safe to re-run. See [docs/deploy-local.md §4](../docs/deploy-local.md#4-one-time-setup) for what each step does and how to run them individually.

Then start the service:

```bash
cd BackEnd
uv run python src/main.py
```

The API is served on `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`. See the repo-root `run-web-debug.ps1` for a script that starts both `BackEnd` and `Web` together.

## Tests

```bash
cd BackEnd
uv run pytest tests/ -v
```

Covers the session-token format (`tests/test_jwt_auth.py`) and the rule that every `/api/` route requires a token (`tests/test_route_auth.py`). The suite is hermetic — a fixture generates throwaway key pairs in a temp directory, so it needs no `keys/`, no database and no running service. Must be run from `BackEnd/`: `main.py` mounts `www/` by relative path at import time.

## API overview

A representative (non-exhaustive) list of endpoints:

- **Auth:** `POST /api/register-user`, `POST /api/login-user`
- **LLM config:** `GET/POST/PUT/DELETE /api/llms`, `/api/llms/{llm_id}`
- **Channel/prompt config:** `GET/POST/PUT/DELETE /api/channels`, `/api/prompts` (and their `{id}` variants)
- **Content generation:** `POST /api/llm-invoke/`, `POST /api/persist-content/`, `POST /api/get-history/`
- **Brainstorming/projects:** `POST /api/brainstorm-idea`, `GET /api/get-project-brainstorming-ideas`, `POST /api/generate-project-items`, `POST /api/save-project`
- **Voice/story tools:** `POST /api/findYourVoice` (disabled by default), `GET/POST/PUT/DELETE /api/voices`, `GET/PUT /api/projects/{project_id}/voice`, `GET /api/get-story-ideas`

Nearly all routes require a bearer JWT (see `Web/` for how tokens are issued).

## Container / production

The repo-root `Dockerfile` builds both `BackEnd` and `Web`, and `supervisord.conf` runs three processes: the Streamlit `Web` app (default port 8501), this FastAPI service (default 8000), and a `sqlite-web` admin UI (default 8080) over the shared database. Each takes its port from an env var (`LOCOL_WEB_PORT`, `LOCOL_BACKEND_PORT`, `LOCOL_SQLITE_WEB_PORT`) whose default is set in the `Dockerfile` — supervisord won't start if one is unset, so override them rather than clearing them. See [docs/deploy-k8s.md](../docs/deploy-k8s.md) for Kubernetes-specific setup.
