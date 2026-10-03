# Running Locol Content AI with Docker Compose

This is the shortest path to a running install: one container on one host, started from a
release download, with no clone and no toolchain. It suits a personal install, a team of
a few people behind a VPN or a reverse proxy, and trying the app out.

For a developer setup with the native Python toolchain see
[deploy-local.md](./deploy-local.md); for a multi-user production deployment with TLS,
Secrets and persistent volumes see [deploy-k8s.md](./deploy-k8s.md). All three run the
same code — the compose path runs the *same image* as Kubernetes
([release.md](./release.md)).

## 1. What you get

One container, three processes under supervisord, exactly as in
[application-architecture.md](./application-architecture.md):

| Process | Container port | Published by compose |
|---|---|---|
| Web (Streamlit) — the UI | 8501 | yes → `http://localhost:8501` |
| BackEnd (FastAPI) — API, Content Editor at `/www`, docs at `/docs` | 8000 | yes → `http://localhost:8000` |
| sqlite-web — database admin UI | 8080 | **no** — see [§7](#7-why-sqlite-web-is-not-published) |

Both published ports are needed. The Content Editor runs in your browser and calls the
BackEnd directly, so `:8000` is not an internal detail — see
[content-editor-flow.md](./content-editor-flow.md).

State lives in two bind-mounted directories next to the compose file, not in the
container:

```
data/
  keys/   private_key.pem, public_key.pem, enc_private_key.pem, enc_public_key.pem
          db_encryption.key
  db/     persistent_data.sqlite      accounts
          users/<user_id>.sqlite      one database per account
```

## 2. Get the package

Every published release carries a ready-to-run archive built from
[`deploy/compose/`](../deploy/compose) by
[`publish-container.yml`](../.github/workflows/publish-container.yml):

```bash
gh release download v0.2.0 --pattern 'locol-content-ai-*.tar.gz'
tar -xzf locol-content-ai-0.2.0.tar.gz
cd locol-content-ai-0.2.0
```

Or download the `.zip` from the release page. It holds `docker-compose.yml`,
`.env.example`, a quickstart `README.md`, the licence files, and the two empty `data/`
directories.

**The compose file in the archive is pinned to that release's image** (`:0.2.0`, not
`:latest`), so the download is reproducible — the workflow fails rather than ship a
floating tag. The copy in the repository is not pinned: it tracks
`${LOCOL_IMAGE_TAG:-latest}`, which is what you want from a clone.

Running from a clone works too, and is the same two commands:

```bash
cd deploy/compose
docker compose up -d
```

## 3. Start it

```bash
docker compose up -d
docker compose logs -f
```

Then open `http://localhost:8501`, register an account, and set a provider key in
**⚙️ Config Manager → 🤖 LLMs → 🤖 Locol AI Default → API Key**. That is the recommended
place for it — encrypted at rest, scoped to one account, never in a file git can see
([deploy-local.md §4.3](./deploy-local.md#43-the-llm-provider-key) covers why the
alternative is worse).

Requirements: Docker with the Compose plugin (Docker Desktop includes it) and ~2 GB of
disk. No Python, no `uv`, no `openssl` on the host — all three are inside the image.

## 4. What the first start creates

This is the part that differs from every other deployment. The image's entrypoint,
[`scripts/docker-entrypoint.sh`](../scripts/docker-entrypoint.sh), creates whatever
start-up artifact is missing before handing off to supervisord, so an empty `./data`
becomes a working install with no setup step:

| Artifact | Created by | Notes |
|---|---|---|
| The four session-token PEMs in `/keys` | [`generate-jwt-keys.sh`](../scripts/generate-jwt-keys.sh) | All four or none. Cheap to regenerate: it only ends existing sessions |
| `db_encryption.key` in `/keys` | [`generate-db-encryption-key.sh`](../scripts/generate-db-encryption-key.sh) | **Back this up.** See [§5](#5-back-up-datakeysdb_encryptionkey) |
| `BackEnd/db/persistent_data.sqlite` | [`create_user_database.py`](../scripts/create_user_database.py) | The accounts table. Per-user databases are still created at registration |

They are the same three generators [`setup-local.sh`](../scripts/setup-local.sh) runs on a
host, called with the container's paths — one implementation of each artifact, not a
second copy of the key generation.

The contract matches that installer's, too, and is what makes a restart safe:

- **Every step detects whether it is already done** and reports `already present`. A
  second start touches nothing.
- **Nothing is ever overwritten or regenerated.** It never passes `--force`.
- **A half-present set is an error, not something to repair.** Three of four PEMs, or a
  `persistent_data.sqlite` that is not a SQLite file, exits non-zero with a message
  naming the file. A mismatched key pair fails on every login, so guessing which half to
  replace would turn a clear failure into a silent one.
- **Both the key paths it writes come from the variables the app reads** —
  `LOCOL_JWT_KEYS_LOCATION` and `LOCOL_DB_ENCRYPTION_KEY_LOCATION` — so it cannot write
  somewhere the services do not look.

Set `LOCOL_BOOTSTRAP=false` to skip the whole thing, for a deployment that provisions
every artifact itself and wants a missing one to fail loudly at first use instead.

The entrypoint is in the image, so it runs for *any* way of starting that image.
Kubernetes gets the keys from Secrets, so there it finds them present, skips, and creates
only `persistent_data.sqlite` on a fresh volume — see
[deploy-k8s.md §4](./deploy-k8s.md#4-generate-keys-create-secrets-and-the-question-sets-configmap).

## 5. Back up `data/keys/db_encryption.key`

Before storing anything real. That file encrypts the `APIkey` column of every user's
`llms` table ([db_crypto.py](../BackEnd/src/db_crypto.py)). There is one key for all
users, no rotation path in the codebase, and no copy other than the file.

Lose it and every stored provider key is permanently unreadable. The failure is at least
loud — [`decrypt_value`](../BackEnd/src/db_crypto.py) raises rather than guessing, and
leaves the stored value alone, so putting the original key back recovers everything. But
nothing else will. [llm-keys.md](./llm-keys.md) has the full picture.

A file copy of `./data` with the stack stopped (`docker compose down`) is a complete
backup; restoring is the reverse. The four `.pem` files are the one part that is cheap to
lose.

## 6. Reaching it from another machine

The defaults assume you browse from the host running the container. `LOCOL_API_URL` and
`LOCOL_WWW_URL` are handed to your *browser*
([apiClient.py](../Web/src/locol-lib/apiClient.py)), so from anywhere else they must name
an address the browser can reach. Copy `.env.example` to `.env` and set both:

```ini
LOCOL_API_URL=http://192.168.1.10:8000
LOCOL_WWW_URL=http://192.168.1.10:8000
```

Set them if you change `LOCOL_BACKEND_PORT` too — that variable moves the *published*
port, and these two URLs are the only thing that has to follow it. (The ports inside the
container are fixed by the compose mappings; nothing else needs to stay in step.)

Behind a reverse proxy terminating TLS, both become the public `https://` URL. Give the
proxy a read timeout above `LOCOL_LLM_REQUEST_TIMEOUT` (default 180s) or it returns a 504
of its own before the app can report the timeout itself — the same constraint
[05-ingress.yaml](../k8s/05-ingress.yaml) carries in Kubernetes.

There is no TLS and no authentication in front of this stack. Fine on a machine you alone
use; put a proxy in front of it before anyone else can reach it, and read
[security-management.md](./security-management.md).

## 7. Why sqlite-web is not published

The image runs sqlite-web on port 8080 and the compose file leaves it unpublished, as a
commented-out line. It has no login and permits writes to `persistent_data.sqlite` — so
publishing it is an unauthenticated editor for every account on the network. The
Kubernetes ingress does not route it either.

To inspect data from the host only:

```yaml
- "127.0.0.1:8080:8080"
```

Never plain `"8080:8080"`, which binds every interface. Reading the files directly is
usually easier anyway:

```bash
uvx sqlite-web data/db/persistent_data.sqlite
```

## 8. Upgrading

The archive's pinned tag means upgrades are deliberate. Either download the newer release
package and move your `./data` (and `.env`) across, or point the current one at a newer
image in `.env`:

```ini
LOCOL_IMAGE_TAG=0.3.0
```

```bash
docker compose pull && docker compose up -d
```

Data survives: it is on the host, and the entrypoint finds every artifact present and
changes nothing. Rolling back is re-pinning the older tag the same way — version tags are
immutable ([release.md](./release.md#rolling-back)).

## 9. Configuration reference

The compose file reads these from `.env`; `.env.example` documents each one. Full
variable reference, including the ones that only apply to a native run, is
[deploy-local.md §9](./deploy-local.md#9-configuration-reference).

| Variable | Default | Purpose |
|---|---|---|
| `LOCOL_IMAGE_TAG` | `latest` (pinned in a release archive) | Which published image to run |
| `LOCOL_WEB_PORT` | `8501` | Published port for the UI. Host-side only |
| `LOCOL_BACKEND_PORT` | `8000` | Published port for the API and Content Editor. Host-side only |
| `LOCOL_API_URL` | `http://localhost:8000` | What the browser calls for the API. See [§6](#6-reaching-it-from-another-machine) |
| `LOCOL_WWW_URL` | `http://localhost:8000` | Base URL for Content Editor links |
| `LOCOL_LLM_REQUEST_TIMEOUT` | `180` | Seconds the UI waits on an LLM-backed request |
| `DEBUG` | `false` | Verbose LLM/request logging |
| `LOCOL_BOOTSTRAP` | *(on)* | Set `false` to skip artifact creation entirely ([§4](#4-what-the-first-start-creates)) |

`.env` is read by Compose to fill in the `${...}` references, and deliberately **not**
passed into the container with `env_file`: the names used above for the *published* ports
are the same ones the app reads for the ports it *binds*, and injecting them would move
the processes out from under the mappings.

The seed config (channels, LLM definitions, prompt templates) and the survey question
sets are baked into the image and need no volume. To change them, see
[deploy-local.md](./deploy-local.md) and rebuild, or mount over
`/app/BackEnd/config` and `/app/Web/question-sets`.

The Bifrost LLM gateway ([llm-keys.md](./llm-keys.md)) is off here: with
`LOCOL_BIFROST_ENABLED` unset, every LLM call goes straight to the provider with the key
on the user's own row. It is a multi-user spend-control layer, and
[deploy-k8s.md](./deploy-k8s.md#optional-the-bifrost-llm-gateway) is where it belongs.

## 10. Troubleshooting

- **A permission error naming `/keys` or `/app/BackEnd/db`, or
  `cannot write ... to /keys`.** On Linux `./data` must be writable by UID 1000, the user
  the image runs as. Docker creates a *missing* bind-mount source itself, as root — which
  is why the archive ships both directories. Fix with
  `sudo chown -R 1000:1000 ./data`. Docker Desktop on Windows/macOS handles this itself.
- **`found an incomplete set of session-token keys`.** Some of the four PEMs in
  `data/keys` are missing or truncated. Restore the missing file, or delete all four and
  restart to regenerate the set — that only ends existing sessions. Never do the
  equivalent for `db_encryption.key` ([§5](#5-back-up-datakeysdb_encryptionkey)).
- **`exists but is not a usable SQLite database`.** `persistent_data.sqlite` is there but
  not a SQLite file. Nothing overwrites it, because that state is more likely a damaged
  database than a disposable one. Move it aside and restart — note that orphans the
  per-user databases beside it, which are named by the user ids it holds.
- **`port is already allocated`.** Set `LOCOL_WEB_PORT` / `LOCOL_BACKEND_PORT` in `.env`,
  and the two URLs to match if you moved the second ([§6](#6-reaching-it-from-another-machine)).
- **The container is `unhealthy` but the app works.** The healthcheck polls Streamlit's
  `/_stcore/health` and allows 60s of start-up, which covers generating an RSA key pair
  on a slow host. If it is persistent, `docker compose logs` has the reason.
- **Login fails, or the logs show `unable to open database file`.** `./data` is not the
  directory this install was set up in, or was restored incompletely.
- **The Content Editor opens blank, or saving a draft fails.** The browser cannot reach
  `LOCOL_WWW_URL` / `LOCOL_API_URL` ([§6](#6-reaching-it-from-another-machine)).
- **Content generation returns an error about the provider key.** No key is set on your
  account yet — Config Manager, per [§3](#3-start-it). The container never reads one from
  the environment.
