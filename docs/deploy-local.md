# Running Locol Content AI locally

This guide sets up Locol Content AI on a developer machine for local use and development,
using the native Python toolchain ([uv](https://docs.astral.sh/uv/)). For a
production Kubernetes deployment, see [deploy-k8s.md](./deploy-k8s.md) instead.

## 1. Overview

You run two Python services side by side (the same two that ship together in the
container image):

| Service | Default port | URL |
|---|---|---|
| BackEnd (FastAPI) | 8000 | `http://localhost:8000` (API + `/docs`) |
| Web (Streamlit) | 8501 | `http://localhost:8501` (main UI) |
| Content Editor | — | served by BackEnd at `http://localhost:8000/www/index.html` |
| sqlite-web (optional) | 8080 | DB admin UI, started manually when needed |

Every port is configurable — see the `LOCOL_*_PORT` variables in
[section 9](#9-configuration-reference). The URLs above assume the defaults.

The Content Editor is prebuilt and committed (`BackEnd/www/`), so it works out of
the box — you only rebuild it if you change its source (see step 7). For how it
talks to BackEnd and how `Web` hands off to it, see
[content-editor-flow.md](./content-editor-flow.md).

## 2. Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — the package/dependency manager both
  services use. This is the only thing you have to install: uv provisions its own
  Python 3.12+ interpreter, so you don't need a system Python.
- **git**
- **PowerShell 5.1+** (bundled with Windows) or **`openssl`** (preinstalled on
  macOS/Linux) — used by the key generation in step 4. Nothing to install.
- **Node.js 18+** — *only* if you plan to modify the Content Editor (step 7).

## 3. Clone the repo

```bash
git clone <your-fork-or-repo-url> locol-ai-agent
cd locol-ai-agent
```

## 4. One-time setup

Run the installer from the repo root. It does every setup step in order and
prints a summary of what it created:

**Windows (PowerShell):**

```powershell
./scripts/setup-local.ps1
```

**macOS / Linux:**

```bash
./scripts/setup-local.sh
```

It performs six steps:

| # | Step | Result |
|---|---|---|
| 1 | Check prerequisites | Fails early with install instructions if `uv` (or, on Unix, `openssl`) is missing |
| 2 | Generate the JWT key pairs | `keys/private_key.pem`, `keys/public_key.pem`, `keys/enc_private_key.pem`, `keys/enc_public_key.pem` |
| 3 | Generate the database encryption key | `keys/db_encryption.key` |
| 4 | Create the shared users database | `BackEnd/db/persistent_data.sqlite` |
| 5 | Install dependencies | `uv sync` in both `BackEnd/` and `Web/` |
| 6 | Offer to configure an LLM provider key | Recommends setting it in the app; only writes `BackEnd/config/default/llms/llm.yaml` if you opt in |

Only step 6 asks you anything, and its default is no — press Enter and the
installer leaves `llm.yaml` untouched. Everything else runs unattended.

**Options** (`-Name value` in PowerShell, `--name value` in Bash):

| Option | Effect |
|---|---|
| `-ApiKey` / `--api-key` | Provider key for step 6. Passing it **is** the opt-in — it writes `llm.yaml` without asking |
| `-ApiStyle` / `--api-style` | Provider style for that key: `openai` (default), `gemini`, `anthropic`, `ollama`, … |
| `-Model` / `--model` | Optional model id, e.g. `google-gla:gemini-2.0-flash` |
| `-SkipLlm` / `--skip-llm` | Leave `llm.yaml` alone without asking. Already the default; this just suppresses the question |
| `-SkipSync` / `--skip-sync` | Skip step 5 (`run-web-debug.ps1` syncs both projects anyway) |
| `-NonInteractive` / `--non-interactive` | Never prompt — for CI. Without a key, `llm.yaml` is left alone |

```powershell
./scripts/setup-local.ps1 -ApiStyle gemini -ApiKey "AIza..." -Model "google-gla:gemini-2.0-flash"
```

**It is safe to re-run.** Every step detects whether it is already done and
reports `already present` rather than redoing it, so running the installer on a
working install changes nothing. In particular it **never** passes `-Force` /
`--force` to the key generators — see the warning in
[§4.1](#41-the-keys-it-generates) for why that matters. To deliberately replace
something, run that step's own script yourself.

> **`… is not digitally signed` / `cannot be loaded`?** PowerShell's execution
> policy is blocking local scripts. Run it for this session only with
> `powershell -ExecutionPolicy Bypass -File ./scripts/setup-local.ps1`.

### 4.1 The keys it generates

Steps 2 and 3 delegate to `scripts/generate-jwt-keys.ps1` / `.sh` and
`scripts/generate-db-encryption-key.ps1` / `.sh`, which you can also run
directly — to regenerate a key, or to produce keys for another environment.

They need no Python or `uv`: the PowerShell versions use .NET (stock Windows
PowerShell 5.1 is enough) and the Bash versions use `openssl` (preinstalled on
macOS/Linux). They resolve their default output directory from their own
location in `scripts/`, so they always write to the repo-root `keys/` directory
regardless of where you invoke them from. `keys/` is gitignored (and
dockerignored); nothing in it is ever committed or baked into an image.

Neither script will clobber existing files: if a key is already present they exit
with an error unless you pass `-Force` / `--force`.

**JWT key pairs**

```powershell
./scripts/generate-jwt-keys.ps1 [-OutDir DIR] [-KeySize N] [-Force]
```
```bash
./scripts/generate-jwt-keys.sh [--out-dir DIR] [--key-size N] [--force]
```

Writes four files — two pairs, one per layer of the session token:

| File | Contents | Held by |
| --- | --- | --- |
| `keys/private_key.pem` | RSA private key, PKCS#1 PEM, unencrypted, `chmod 600` (Windows: best-effort ACL restricted to the current user) | Web — **signs** |
| `keys/public_key.pem` | Matching public key, SubjectPublicKeyInfo PEM | BackEnd — **verifies** |
| `keys/enc_private_key.pem` | EC P-256 private key, SEC1 PEM, unencrypted, same permissions as above | BackEnd — **decrypts** |
| `keys/enc_public_key.pem` | Matching public key, SubjectPublicKeyInfo PEM | Web — **encrypts** |

`-KeySize` / `--key-size` applies only to the RSA pair (default 2048; override with
`4096`). The EC curve is fixed at P-256 by the token format.

The token is a signed JWT sealed inside an encrypted one: Web signs it with the RSA
private key (RS256) and encrypts the result to BackEnd's EC public key
(ECDH-ES+A256KW / A256GCM); BackEnd decrypts with its EC private key and then
verifies the signature with the RSA public key. Note the halves are held crosswise
— each service has one private key and one public key, so neither can both mint and
read a token alone. Both read the directory from `LOCOL_JWT_KEYS_LOCATION` (see §9)
and must point at the same four files, or every login fails.
[docs/jwt.md](./jwt.md) explains the whole scheme in plain language.

Regenerating these pairs is cheap: it only invalidates existing sessions, so users
simply log in again.

**Database encryption key**

```powershell
./scripts/generate-db-encryption-key.ps1 [-OutDir DIR] [-Force]
```
```bash
./scripts/generate-db-encryption-key.sh [--out-dir DIR] [--force]
```

Writes one file:

| File | Contents |
| --- | --- |
| `keys/db_encryption.key` | A URL-safe base64 Fernet key — 32 random bytes (AES-128-CBC + HMAC-SHA256), `chmod 600` / restricted ACL |

BackEnd reads it from `LOCOL_DB_ENCRYPTION_KEY_LOCATION` (see §9) and uses it to
encrypt the `APIkey` column of every per-user `llms` table at rest — see
[BackEnd/src/db_crypto.py](../BackEnd/src/db_crypto.py). The key is loaded once
per process, so a replaced key needs a BackEnd restart to take effect.

> **Warning — this key is not disposable.** Unlike the JWT pair, it protects data
> at rest. There is one key for all users, no rotation path in the codebase, and
> no backup other than this file. If you lose or regenerate it after LLM API keys
> have been saved, those values are permanently unrecoverable. The failure is at
> least loud: anything that won't decrypt raises rather than being guessed at, and
> the stored value is left untouched, so pointing BackEnd back at the original key
> restores everything. Back the file up out of band before you store any real data,
> and only use `-Force` / `--force` on a fresh install. This is why the installer
> never forces.

**Deploying to Kubernetes?** Generate the keys locally with the same two scripts,
then load them into the cluster as secrets (`locol-ai-jwt-keys`, holding all four JWT
key files, and `locol-ai-db-key`) rather than mounting the directory — see
[deploy-k8s.md §4](./deploy-k8s.md#4-generate-keys-create-secrets-and-the-question-sets-configmap).
If you are upgrading a deployment that predates the encrypted session token, update
that secret **before** rolling out the new image; that section explains why.

### 4.2 The users database

Step 4 runs `scripts/create_user_database.py`, which creates
`BackEnd/db/persistent_data.sqlite`, the shared accounts database holding the
`users` table. Per-user databases (`BackEnd/db/users/<user_id>.sqlite`) are
created and seeded automatically when each account registers. This is the one
setup step that runs through `uv` — it reuses the BackEnd's own
`init_users_table()` so there's a single source of truth for the schema.

**Don't skip it.** Nothing in the running app creates the `BackEnd/db/`
directory, so a missing accounts database doesn't self-heal — registration and
login fail with `unable to open database file`. To run just this step:

```bash
uv run --project BackEnd python scripts/create_user_database.py
```

The script refuses to touch an existing file unless you pass `--force`, so it's
safe to run when you're unsure. `--db-path` puts the database somewhere else,
though the BackEnd only ever looks for it at the default location, relative to
its own working directory.

### 4.3 The LLM provider key

Content generation needs a real LLM provider key. There are two places to put
one, and they are not equivalent.

**Recommended — set it in the app.** Start the services, register an account,
then:

**⚙️ Settings and Tools** → **⚙️ Config Manager** → tab **🤖 LLMs** → expand
**🤖 Locol AI Default** → fill in **API Key** → **💾 Update**

A key set this way is encrypted at rest with the Fernet key from
[§4.1](#41-the-keys-it-generates) (see [llm-keys.md](./llm-keys.md)), belongs to
that one account, and never touches a file git can see. This is what step 6 of
the installer points you at, and it is why step 6 defaults to changing nothing.

**The alternative — edit `llm.yaml`.** The checked-in
`BackEnd/config/default/llms/llm.yaml` ships with a placeholder key. The
installer will write a real one into it if you opt in at the step 6 prompt, or
if you pass `-ApiKey` / `--api-key`. You can also edit it by hand — pick the
provider you'll use (Gemini, Claude, OpenAI, or a local model), changing only the
provider fields:

```yaml
id: "default"
name: "Locol AI Default"
APIstyle: "gemini"
APIkey: "your-real-key-here"
model: "google-gla:gemini-2.0-flash"
```

> **Keep the `name` as `Locol AI Default`.** That exact string is the marker
> Bifrost provisioning matches on to find the row
> ([bifrost_manager.py](../BackEnd/src/bifrost_manager.py)); renaming it means a
> deployment silently never provisions a virtual key. See
> [deploy-k8s.md](./deploy-k8s.md#optional-the-bifrost-llm-gateway).

> **Unlike `keys/`, `llm.yaml` is tracked by git.** A key written here can be
> committed into your own repo by accident — check
> `git diff -- BackEnd/config/default/llms/llm.yaml` before committing. It is
> also a *seed*: every user's database gets a copy of it at registration, so one
> key here is shared by everyone rather than belonging to you. That is the
> problem the Bifrost gateway exists to solve —
> [llm-keys.md §7](./llm-keys.md#7-the-problem-the-drawer-doesnt-solve).

> **One caveat on the in-app route.** A key you set in Config Manager is not
> permanently immune to the seed. A full config resync rewrites the
> `Locol AI Default` row from the YAML
> ([load_llms.py](../BackEnd/src/load_llms.py)), so if `llm.yaml` still holds the
> placeholder, a resync replaces your working key with it. Rows holding a Bifrost
> virtual key are exempt; a hand-entered key is not. Nothing in normal use
> triggers this — re-enter the key in Config Manager if it ever happens.

`SERPER_API_KEY` is **not needed**. It only fed the Reddit writing-style analyzer on the
Find Your Voice page, which is disabled because Reddit blocks the automated access it
relied on — saved voices are written by hand instead. If you want to try the analyzer
anyway, set both variables on both services before starting them:

```bash
export LOCOL_FIND_YOUR_VOICE_ENABLED=true      # macOS/Linux
export SERPER_API_KEY=<your-serper-key>
$env:LOCOL_FIND_YOUR_VOICE_ENABLED = "true"    # Windows PowerShell
$env:SERPER_API_KEY = "<your-serper-key>"
```

## 5. Run

The installer does not start anything — launch the services yourself.

### Windows quickstart

From the repo root:

```powershell
./run-web-debug.ps1
```

This syncs both projects, starts the BackEnd in its own window (port 8000), waits
for it to become reachable, then runs the Web app in the foreground (port 8501).
`Ctrl+C` in the Web window stops both. It re-checks the step 4 setup first and
refuses to start if anything is missing.

### Manual (macOS / Linux / any OS)

Use two terminals.

**Terminal 1 — BackEnd** (from `BackEnd/`):

```bash
cd BackEnd
uv run python src/main.py
```

**Terminal 2 — Web** (from `Web/`):

```bash
cd Web
uv run streamlit run src/main.py --server.port=8501
```

The default environment variables already point Web at
`http://localhost:8000`, and the BackEnd finds the repo-root `keys/` and
`BackEnd/config/` directories automatically — so no extra configuration is needed
for a standard local run.

## 6. Access the app

- **Web UI:** `http://localhost:8501` — register an account, then log in. (User
  accounts live in your local SQLite DB.)
- **API docs:** `http://localhost:8000/docs`
- **Content Editor:** `http://localhost:8000/www/index.html`

## 7. Optional: build the Content Editor

Only needed if you're changing the editor's source under `FrontEnd/`. It builds
straight into `BackEnd/www/`, which the BackEnd serves.

```bash
cd FrontEnd
npm install
npm start        # dev server with live reload
npm run build    # production build → ../BackEnd/www/
```

See [FrontEnd/README.md](../FrontEnd/README.md) for details.

## 8. Optional: inspect the database

To browse the local SQLite data with a web UI:

```bash
uvx sqlite-web BackEnd/db/persistent_data.sqlite
```

Per-user data lives in separate files under `BackEnd/db/users/<user_id>.sqlite`.

## 9. Configuration reference

Every variable below has a working local default, so you normally don't need to
set any of them:

| Env var | Local default | Purpose |
|---|---|---|
| `LOCOL_BACKEND_PORT` | `8000` | Port the BackEnd binds, and the port the two URLs below default to. |
| `LOCOL_WEB_PORT` | `8501` | Port the Streamlit app binds. `run-web-debug.ps1` uses it as the default for `-WebPort`; running Streamlit by hand takes `--server.port`. |
| `LOCOL_SQLITE_WEB_PORT` | `8080` | Port the sqlite-web admin UI binds inside the container image. |
| `LOCOL_USER_DB_PORT` | `8081` | Port `BackEnd/start_user_db.sh` serves one user's database on. |
| `LOCOL_API_URL` | `http://localhost:8000` | Web → BackEnd base URL. Follows `LOCOL_BACKEND_PORT` unless set explicitly. |
| `LOCOL_WWW_URL` | `http://localhost:8000` | Base URL for Content Editor links. Same default as above. |
| `LOCOL_CONFIG_LOCATION` | `./config` | Seed config dir (resolves to `BackEnd/config`). |
| `LOCOL_JWT_KEYS_LOCATION` | `../keys` | JWT keypair dir (resolves to repo-root `keys/`). |
| `LOCOL_DB_ENCRYPTION_KEY_LOCATION` | `../keys` | DB encryption key dir (repo-root `keys/`). |
| `LOCOL_LLM_REQUEST_TIMEOUT` | `180` | Seconds the Web app waits on an LLM-backed request. |
| `LOCOL_FIND_YOUR_VOICE_ENABLED` | *(unset — off)* | Re-enables the Reddit writing-style analyzer, which is off because Reddit blocks it. Set on both BackEnd and Web, or neither. |
| `SERPER_API_KEY` | *(unset)* | Only used by that analyzer, and only when it is enabled. |
| `LOCOL_BIFROST_ENABLED` | *(unset — off)* | Routing through the Bifrost LLM gateway, which local runs don't use. Left off, every LLM call goes straight to the provider using the key seeded from `BackEnd/config/default/llms/llm.yaml`. It's on in K8s. |
| `DEBUG` | *(unset)* | Set `true` for verbose LLM/request logging. |

See [BackEnd/README.md](../BackEnd/README.md#configuration) for the full reference.

## 10. Troubleshooting

- **Port already in use (8000 or 8501):** another process is bound to the port.
  Stop it, or move the service: `.\run-web-debug.ps1 -BackendPort 9000 -WebPort 9501`,
  or set `LOCOL_BACKEND_PORT` / `LOCOL_WEB_PORT` before starting the services by hand.
  `LOCOL_BACKEND_PORT` also shifts the Web app's default `LOCOL_API_URL`, so the two
  stay pointed at each other. (`run-web-debug.ps1` refuses to start on an occupied
  BackEnd port rather than silently talking to the stale process.)
- **`SERPER_API_KEY environment variable is not set`:** only reachable if you re-enabled
  the Reddit analyzer with `LOCOL_FIND_YOUR_VOICE_ENABLED`. Export the key (§4.3) and
  restart the BackEnd, or leave the analyzer off and write voices by hand.
- **`FileNotFoundError` for `private_key.pem` / `enc_public_key.pem` /
  `db_encryption.key`, or a 500 `Server authentication key is not configured` from
  the BackEnd:** the one-time
  setup (step 4) hasn't run or the `keys/` directory is missing — re-run
  `./scripts/setup-local.ps1` (or `.sh`). It creates whatever is absent and leaves
  the rest untouched.
- **Registration or login fails with no useful message, or the BackEnd logs
  `unable to open database file`:** `BackEnd/db/persistent_data.sqlite` is missing —
  step 4 hasn't run. Nothing in the app creates the `db/` directory, so this does
  not self-heal; re-run `./scripts/setup-local.ps1` (or `.sh`) from the repo root.
  `./run-web-debug.ps1` checks for this before starting anything.
- **The installer stops with "found one half of the JWT keypair but not the
  other":** one of the two `.pem` files was deleted or truncated. It won't
  overwrite the survivor, so regenerate both deliberately with
  `./scripts/generate-jwt-keys.ps1 -Force` — that only invalidates existing
  sessions.
- **`Failed to canonicalize script path` (Windows), with nothing else on the line:**
  the checkout was moved or renamed after its virtual environments were created. uv
  writes the absolute path of each venv's `python.exe` into every console-script
  `.exe` it installs (`streamlit.exe`, `uvicorn.exe`, …), and `uv sync` does not
  rewrite them — the packages are still installed, so there is nothing for it to do.
  Rebuild the launchers in both projects:
  `uv sync --reinstall --project BackEnd` and `uv sync --reinstall --project Web`.
  Deleting both `.venv` directories works too, and takes longer. `run-web-debug.ps1`
  checks for this before launching either service and names the stale path.
- **`… is not digitally signed` / `cannot be loaded` when running a `.ps1`:**
  PowerShell's execution policy is blocking local scripts. Run them for the
  current session with
  `powershell -ExecutionPolicy Bypass -File ./scripts/setup-local.ps1`.
