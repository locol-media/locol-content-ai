# Locol Content AI

---

![Your story, told in your voice — Locol Content AI plans, writes, and refines your Reddit posts, capturing exactly how you talk. Sounds like you, not a chatbot; your expertise, already a story; a sharpened angle before you write; you're always the final review.](./cover.png)

---

An AI-assisted tool for telling your story on Reddit — end to end, from "what do I even have to say?" through to a finished post.

## Overview

Reddit is unforgiving toward marketing and generous toward people. A promotional post
gets downvoted into silence; a genuinely useful one — someone sharing what they
learned the hard way — earns replies, questions, and trust. The difference is not
tone or polish. It is whether the post gives a community something it did not have
before.

Locol Content AI is built around that constraint. It does not help you advertise on Reddit;
it helps you work out which parts of your experience are worth a community's
attention, and then tell them as a series of posts that earn their place. The value
you offer comes first, and your business follows from it.

To do that it manages the whole cycle in one place:

1. **Find what you know.** A survey draws out your business, your professional
   expertise, and — just as importantly — your hobbies and interests. Hard-won
   knowledge and genuine enthusiasm are what a subreddit responds to; a product
   description is not.
2. **Find the stories in it.** The AI reads that material back and proposes personal
   stories worth telling, each framed as a narrative rather than a pitch, with a
   reason the audience should care and suggested subreddits where it would land.
3. **Break a story into a series.** A chosen story becomes a project with its own
   survey to sharpen the angle, then a set of individual posts — the first
   introducing the series, the rest developing it — each with its own purpose,
   Reddit post format, and the business goal it quietly serves.
4. **Write it in your voice.** Drafts are generated per post from configurable prompt
   templates, optionally steered by a saved writing-style profile you pick per project,
   then finished by hand in a built-in rich-text editor with the AI on call for
   re-writes.

Everything you produce stays yours: each account gets its own database, and nothing
is posted anywhere. The tool takes you as far as a finished draft — publishing, and
the judgment about which community it genuinely belongs in, remain with you.

For a click-by-click walkthrough of the whole cycle, see
[docs/how-to-use.md](./docs/how-to-use.md).

## How it's put together

Three components share one backend:

- **[BackEnd](./BackEnd)** — a FastAPI service that owns accounts, per-user data (SQLite, one database per user), LLM configuration, and content-generation/brainstorming logic. Both UI surfaces below talk to it as their API.
- **[Web](./Web)** — a Streamlit app that's the main entry point: login/registration, a business survey, campaign brainstorming, and configuration (which LLMs/channels/prompts are available).
- **[FrontEnd](./FrontEnd)** — the source project for the Content Editor, a rich-text authoring UI (built on [Quill](https://quilljs.com/) via a customized fork of [stencil-quill](https://github.com/KillerCodeMonkey/stencil-quill)). It's built as static assets served directly by `BackEnd`, not run as its own service.

```
Web (Streamlit, :8501*) ──┐
                           ├──▶ BackEnd (FastAPI, :8000*) ──▶ SQLite (per user) + LLM providers
FrontEnd (built into /www)┘        (OpenAI / Gemini / Claude / local)
```

<sub>* Default ports — both are configurable via `LOCOL_WEB_PORT` / `LOCOL_BACKEND_PORT`; see [docs/deploy-local.md](./docs/deploy-local.md#9-configuration-reference).</sub>

See each subproject's README for details: [BackEnd](./BackEnd/README.md), [Web](./Web/README.md), [FrontEnd](./FrontEnd/README.md). For how `Web` hands off to the Content Editor and what happens from there — the endpoints, payloads and the round trip back — see [docs/content-editor-flow.md](./docs/content-editor-flow.md).

## Getting started

- **Using the app** — the full workflow, stage by stage: [docs/how-to-use.md](./docs/how-to-use.md)
- **Architecture** — the components, the request path, where state lives, and what a production deployment looks like: [docs/application-architecture.md](./docs/application-architecture.md)
- **Docker Compose** — the shortest path to a running install: download a release package, `docker compose up -d`, no clone and no toolchain. It creates its own keys and database on the first start: [docs/deploy-compose.md](./docs/deploy-compose.md)
- **Local development** — prerequisites, one-time key/database setup, running both services and building the Content Editor: [docs/deploy-local.md](./docs/deploy-local.md)
- **Kubernetes (EKS / DigitalOcean)** — image build, secrets, manifests, DNS/TLS: [docs/deploy-k8s.md](./docs/deploy-k8s.md)
- **Cutting a release** — the GHCR tag scheme, how to publish an image, provenance and rollback: [docs/release.md](./docs/release.md)
- **LLM API keys** — how they're encrypted at rest, and how the Bifrost gateway gives each user a capped, scoped virtual key instead of a shared provider key: [docs/llm-keys.md](./docs/llm-keys.md)
- **Security overview** — the map of every layer, the controls no other document covers, and an honest register of the gaps: [docs/security-management.md](./docs/security-management.md)

## Container images

Prebuilt images are published to GitHub Container Registry, so deploying needs no
local build:

```
ghcr.io/locol-media/locol-content-ai:0.2.0   # a release - immutable, use in production
ghcr.io/locol-media/locol-content-ai:latest  # newest release; moves
ghcr.io/locol-media/locol-content-ai:edge    # newest commit on main; moves
```

One image holds all three processes (FastAPI, Streamlit, sqlite-web) under
supervisord. See [docs/release.md](./docs/release.md) for the full tag scheme and how
releases are cut, and [docs/deploy-k8s.md](./docs/deploy-k8s.md) to deploy one.

Each release also carries a **Docker Compose package** —
`locol-content-ai-<version>.zip` / `.tar.gz` on the release page — holding a compose file
pinned to that version, so running the app is a download and one command. The container
generates its own JWT keys, database encryption key and accounts database on first start,
so there is no setup step: [docs/deploy-compose.md](./docs/deploy-compose.md).

## Tech stack

- **BackEnd:** Python, FastAPI, [pydantic-ai](https://ai.pydantic.dev/) (OpenAI/Gemini/Claude/local model providers), SQLite, nested-JWT auth (RS256 signature inside an ECDH-ES+A256KW/A256GCM JWE), Fernet encryption for secrets at rest.
- **Web:** Python, Streamlit.
- **FrontEnd:** TypeScript, [Stencil.js](https://stenciljs.com/), Quill.

## Security

If you're deploying this yourself: rotate the JWT keypair and DB encryption key before going to production (see [docs/deploy-local.md](./docs/deploy-local.md#41-the-keys-it-generates)), and set your LLM provider key in the app — register an account, then **⚙️ Config Manager → 🤖 LLMs → Locol AI Default**, where it is encrypted at rest. Prefer that to editing `BackEnd/config/default/llms/llm.yaml`, which is tracked by git and seeds every user with the same key ([docs/deploy-local.md §4.3](./docs/deploy-local.md#43-the-llm-provider-key)). See [BackEnd/README.md](./BackEnd/README.md#configuration) for the full configuration reference.

**[docs/security-management.md](./docs/security-management.md) is the entry point.** It maps every layer of the defence — identity, session, tenancy, secrets at rest, spend control, the network edge — says which document owns each one, and covers the controls that have no deep-dive of their own: how per-user database isolation works, how untrusted text is handled, and how the code is scanned. It ends with a register of the gaps that nothing else records.

The three deep-dives it points at are written in plain language and are honest about their own limits: [docs/password-hashing.md](./docs/password-hashing.md) on how passwords are hashed with bcrypt and never stored in recoverable form, [docs/jwt.md](./docs/jwt.md) on the session tokens that keep you logged in afterwards, and [docs/llm-keys.md](./docs/llm-keys.md) on the credential that costs money — encryption at rest, and the budget-capped Bifrost virtual key that replaces a shared provider key.

## License

Copyright (C) 2026 Locol Media. This project is licensed under the [GNU General Public License v3.0](./LICENSE) — [LICENSE](./LICENSE) is a verbatim copy of the license text, and [COPYRIGHT](./COPYRIGHT) carries the project's own copyright notice and grant.

Third-party components vendored into this repository keep their own licenses — [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md) lists each one, its version, and the paths it occupies.

`FrontEnd/` is built on [stencil-quill](https://github.com/KillerCodeMonkey/stencil-quill), which remains under its original MIT license — see [FrontEnd/LICENSE](./FrontEnd/LICENSE) and [FrontEnd/VENDOR_README.md](./FrontEnd/VENDOR_README.md). The Locol-specific additions in that folder are covered by this repository's GPLv3 license: `src/index.html` and the Locol files in `src/includes/` (`auth.js`, `dynamic-*`, `getting-started.js`, `grid-master.*`, `prompt-window.*`, `quill-editor-window.js`) — but *not* the vendored Quill and Intro.js files that also live under `src/includes/`.

One of those vendored components, [Intro.js](https://introjs.com), is licensed under the **AGPL-3.0**. GPLv3 §13 permits the combination, but AGPL §13 then applies to it: if you deploy this application, you must offer its source to users who interact with it over the network — linking this repository from the running app is enough. See [THIRD-PARTY-NOTICES.md](./THIRD-PARTY-NOTICES.md#introjs--agpl-30-or-a-commercial-license) for the detail and the alternatives.
