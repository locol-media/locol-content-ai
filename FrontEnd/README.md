# FrontEnd — Content Editor

This is the source project for the **Content Editor**, the rich-text authoring surface where generated content gets reviewed, edited, and saved. It's a customized build of [stencil-quill](https://github.com/KillerCodeMonkey/stencil-quill), an MIT-licensed Stencil.js wrapper around the [Quill](https://quilljs.com/) rich-text editor, with a Locol-specific application layer built on top of the vendored components.

- The vendored upstream component library (Stencil.js + TypeScript, under `src/components/`) is unmodified and documented in [VENDOR_README.md](./VENDOR_README.md) — see that file and this folder's [LICENSE](./LICENSE) for the original MIT terms.
- Locol's additions — `src/index.html` and Locol's own plain-JavaScript files in `src/includes/` (`auth.js`, `dynamic-*`, `getting-started.js`, `grid-master.*`, `prompt-window.*`, `quill-editor-window.js`; no build step) — implement the actual Content Editor UI: project/item/channel/LLM selection, a resizable multi-pane grid, prompt template selection with tag filtering, dynamic form fields generated from prompt placeholders, and a history view of prior LLM responses. These additions are covered by the repository's overall [GPLv3 license](../LICENSE), not the vendored MIT code.
- `src/includes/` also holds vendored third-party assets that are *not* Locol's and carry their own licenses — Quill under `src/includes/vendor/` (BSD-3-Clause) and Intro.js as `intro.min.js` / `introjs.min.css` (AGPL-3.0, see [intro.LICENSE](./src/includes/intro.LICENSE)). All of them are listed in [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md).

## How it fits together

This is **not** a standalone hosted app. `stencil.config.ts` builds straight into `../BackEnd/www/`, which [BackEnd](../BackEnd)'s FastAPI service serves as static files at `http://localhost:8000/www/index.html`. That's why it's excluded from the Docker build (`.dockerignore`) and not part of `supervisord.conf` — by the time the container image is built, the compiled output already lives inside `BackEnd/www/`.

The Content Editor calls `BackEnd`'s REST API directly (`/api/get-projects/`, `/api/llm-invoke/`, `/api/persist-content/`, `/api/get-history/`, etc.) and expects a JWT via cookie or `?jwt=...` URL parameter — normally provided by [Web](../Web) when a user clicks through from a generated content idea to "open in Content Editor."

It's a separate UI surface from `Web/` (which handles login, surveys, and brainstorming) — the two don't share code, but both talk to `BackEnd` independently.

[docs/content-editor-flow.md](../docs/content-editor-flow.md) documents that interface end to end: the handoff URL, the bootstrap and selection cascade, how prompt placeholders become input fields, the two write paths, and how an edit finds its way back into the Web idea list. It also records known defects in the flow.

## Running locally

Requires Node.js 18+ and npm.

```bash
npm install

# Dev server with live reload
npm start

# Production build — writes into ../BackEnd/www/
npm run build
```

`src/includes/*.js` has no build step of its own — the `www` output target copies
it verbatim to `../BackEnd/www/includes/`. Edit it **here**, never there: the copy
is overwritten on every build, so a fix applied to `BackEnd/www/includes/` alone
disappears, and until it does the two copies disagree.

Because the Docker build has no Node stage, the regenerated output under
`../BackEnd/www/` has to be committed alongside the `src/` change that caused it.
See [../BackEnd/www/README.md](../BackEnd/www/README.md).

Once built (or once `BackEnd` is running with an existing `www/` build), the editor is served at `http://localhost:8000/www/index.html` by the `BackEnd` service — there's no separate dev port to hit in production use.

No environment variables are required; the page calls `/api/...` relative to whatever origin serves it.
