# Locol Content AI — Docker Compose

An AI-assisted tool for telling your story on Reddit, from "what do I even have to say?"
through to a finished post. This package runs the whole thing — API, web UI and the
Content Editor — as one container on one machine.

You need **Docker** with the Compose plugin ([Docker
Desktop](https://docs.docker.com/desktop/) on Windows or macOS already includes it) and
about 2 GB of disk. Nothing else: no Python, no clone, no setup script.

## Get it

If you are reading this inside an extracted release archive, skip ahead to
[Start it](#start-it).

Otherwise, download **`locol-content-ai-<version>.zip`** (Windows, macOS) or **`.tar.gz`**
(Linux) from the [latest release][releases] — the package, not "Source code" — and
extract it. On a server:

```bash
gh release download --repo locol-media/locol-content-ai --pattern 'locol-content-ai-*.tar.gz'
tar -xzf locol-content-ai-*.tar.gz
cd locol-content-ai-*/
```

## Start it

From the extracted folder:

```bash
docker compose up -d
```

The first start pulls the image (a few minutes) and then creates the files the app needs
to run — the session-token key pairs, the database encryption key, and the accounts
database — into `./data`. Watch it happen:

```bash
docker compose logs -f
```

When the log settles, open **<http://localhost:8501>** and register an account. Accounts
are local to this install; the first one you create is yours.

Then tell it which model to use. Content generation needs this, and the package
deliberately does not ask for a key up front:

1. **⚙️ Settings and Tools** → **⚙️ Config Manager** → tab **🤖 LLMs**
2. Expand **🤖 Locol AI Default**
3. Set **API Style** to your provider — `openai`, `gemini` or `claude`
4. Set **Model** to a model name that provider offers, for example `gpt-4o-mini`,
   `gemini-2.0-flash` or `claude-sonnet-4-5`. The default row ships with no model, so
   this is not optional
5. Paste your key into **API Key**
6. **💾 Update**

Leave **API URL** empty for the three hosted providers. For a local model (Ollama, LM
Studio, vLLM) choose `openai`, set **API URL** to the server's OpenAI-compatible address
— for Ollama on this machine, `http://host.docker.internal:11434/v1` with Docker Desktop
or the host's LAN address on Linux, because `localhost` inside the container is the
container — and leave the key empty if the server takes none.

A key set there is encrypted at rest and belongs to your account only.

From there, [how-to-use.md][how-to-use] walks through the whole cycle: the survey that
draws out what you know, the stories it proposes, turning one into a series of posts, and
writing them in your voice.

## Back up `data/keys/db_encryption.key`

**Do this before you store anything real.** That one file encrypts the LLM API key of
every account. There is one key for all of them, no rotation path, and no copy other than
the file itself — lose it and every stored key becomes permanently unreadable. Copy it
somewhere off this machine now.

The rest of `./data` is worth backing up too, just less urgently:

```
data/
  keys/   private_key.pem, public_key.pem, enc_private_key.pem, enc_public_key.pem
          db_encryption.key          <- the one above
  db/     persistent_data.sqlite     accounts
          users/<user_id>.sqlite     one database per account - all of their content
```

A plain file copy of `./data` with the stack stopped (`docker compose down`) is a
complete backup. Restoring is the reverse: put `./data` back and `docker compose up -d`.
The four `.pem` files are the one part you can afford to lose — regenerate them by
deleting all four, which only logs everyone out.

## Everyday commands

```bash
docker compose ps                  # is it running, and is it healthy
docker compose logs -f             # follow the logs
docker compose restart             # restart it
docker compose down                # stop it; ./data is untouched
docker compose pull && docker compose up -d    # pull and restart (see Upgrading)
```

## Configuration

Copy `.env.example` to `.env` and edit it. Every setting has a working default, so you
only need the file if a port is taken or you reach the app from another machine:

```bash
cp .env.example .env
docker compose up -d
```

The common case is using the app from a *different* machine than the one running it. Set
both URLs to the address your browser uses, because the app hands them to the browser:

```ini
LOCOL_API_URL=http://192.168.1.10:8000
LOCOL_WWW_URL=http://192.168.1.10:8000
```

Both ports have to stay published for that: `:8501` serves the UI, and `:8000` serves the
API and the Content Editor, which your browser calls directly.

## Upgrading

This package pins the image to the release it came from — the `image:` line in
`docker-compose.yml` names an exact version — so an upgrade is deliberate, and
`docker compose pull` on its own changes nothing. Two ways to move up:

- **Take the newer package (recommended).** Stop this one with `docker compose down`,
  extract the newer release, move `./data` (and `.env`, if you made one) into it, and run
  `docker compose up -d` there. You get that release's compose file and README as well.
- **Edit the pin in place.** Change the version at the end of the `image:` line in
  `docker-compose.yml`, for example to `ghcr.io/locol-media/locol-content-ai:0.3.0`, then:

  ```bash
  docker compose pull && docker compose up -d
  ```

  `LOCOL_IMAGE_TAG` in `.env` does **not** do this here: it only applies to the
  unpinned compose file in the repository.

Your data survives: it is in `./data` on the host, not in the container. The entrypoint
finds every artifact already present and changes nothing. Rolling back is the same edit
with the older version — release tags never move.

## If it doesn't start

- **A permission error naming `/keys` or `/app/BackEnd/db`** — on Linux, `./data` has to
  be writable by UID 1000, the user inside the image. This happens when the directories
  were created by Docker rather than by extracting this archive:

  ```bash
  sudo chown -R 1000:1000 ./data
  docker compose up -d
  ```

  Docker Desktop on Windows and macOS handles this itself.

- **`port is already allocated`** — something else holds 8501 or 8000. Change
  `LOCOL_WEB_PORT` / `LOCOL_BACKEND_PORT` in `.env`, and if you change the second one,
  set `LOCOL_API_URL` and `LOCOL_WWW_URL` to match.

- **"found an incomplete set of session-token keys"** — some of the four `.pem` files in
  `data/keys` are gone. Nothing will overwrite the survivors, because a mismatched pair
  fails on every login. Restore the missing file, or delete all four and restart to get a
  fresh set — that only logs people out. It does **not** apply to `db_encryption.key`,
  which is never safe to regenerate once keys have been saved.

- **The web UI loads but login or registration fails** — check `docker compose logs` for
  a key or database error, which almost always means `./data` is not the folder it was
  set up in, or was restored incompletely.

- **The Content Editor opens blank, or saving a draft fails** — your browser cannot reach
  `LOCOL_WWW_URL` / `LOCOL_API_URL`. From another machine these must not say `localhost`;
  see [Configuration](#configuration).

The full guide — what the entrypoint does, the reverse-proxy and Kubernetes paths, and
the configuration reference — is [docs/deploy-compose.md][deploy-compose].

## Security

This stack has no TLS and no reverse proxy. That is fine on a machine you alone use; put
it behind a proxy that terminates HTTPS before exposing it to anyone else, and keep its
read timeout above `LOCOL_LLM_REQUEST_TIMEOUT`.

The database admin UI (sqlite-web, port 8080 inside the container) is intentionally not
published — it has no login and can write to every account's data.
[docs/security-management.md][security] is the map of what is and is not defended.

## License

Copyright (C) 2026 Locol Media. GPLv3 — `LICENSE` is the license text and `COPYRIGHT`
the project's own notice. Third-party components keep their own licenses, listed in
`THIRD-PARTY-NOTICES.md`.

One of them, [Intro.js](https://introjs.com), is **AGPL-3.0**. If you deploy this for
other people to use over a network, you must offer them its source — linking
<https://github.com/locol-media/locol-content-ai> from the running app is enough.

[releases]: https://github.com/locol-media/locol-content-ai/releases/latest
[how-to-use]: https://github.com/locol-media/locol-content-ai/blob/main/docs/how-to-use.md
[deploy-compose]: https://github.com/locol-media/locol-content-ai/blob/main/docs/deploy-compose.md
[security]: https://github.com/locol-media/locol-content-ai/blob/main/docs/security-management.md
