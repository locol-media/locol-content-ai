# BackEnd/www — generated, do not edit

Everything in this directory is **build output**. It is produced by the `www`
output target in [`FrontEnd/stencil.config.ts`](../../FrontEnd/stencil.config.ts):

| Path | Produced by | Source of truth |
|---|---|---|
| `build/` | `stencil build` | `FrontEnd/src/components/` |
| `includes/` | the target's `copy` step | `FrontEnd/src/includes/` |
| `index.html` | `stencil build` | `FrontEnd/src/index.html` |

Edits made here are silently overwritten the next time anyone runs the FrontEnd
build. `includes/` in particular is a verbatim copy — a fix applied here and not
to `FrontEnd/src/includes/` will disappear, and until it does the two copies
disagree.

**To change anything under this directory**, edit the corresponding file under
`FrontEnd/src/` and rebuild:

```
cd FrontEnd
npm install      # first time only
npm run build
```

## Why it is committed

FastAPI serves this directory at `/www` (see
[`BackEnd/src/main.py`](../src/main.py) — `app.mount("/www", StaticFiles(directory="www"))`).

The `Dockerfile` has no Node stage: it copies `BackEnd/` wholesale and never runs
`stencil build`. So the build output has to be committed, or container images
ship without it and the Content Editor loads but renders nothing — the case
`main.py` warns about on startup when `www/build/` is missing.

That means **rebuilt output belongs in the same commit as the `FrontEnd/src`
change that caused it.**

## Scanning

`bearer.yml` skips this directory. It is generated, so findings here are
duplicates of the `FrontEnd/src` findings, reported against a path nobody should
edit.
