# How security is managed here — the overview

This is the map. Three companion documents each explain one security control in depth —
[password-hashing.md](./password-hashing.md) proves who you are,
[jwt.md](./jwt.md) keeps you logged in afterwards, and
[llm-keys.md](./llm-keys.md) looks after the credential that costs money. Each is written
so you don't need a security background to follow it, and each ends by being honest about
its own limits.

What none of them answers is the question this document exists for: **what is the overall
shape of the defence, and which parts of it does nobody else write down?** So this page
does two jobs. It ties the set together, and it covers the controls that have no
deep-dive of their own — how one user's data is kept away from another's, how untrusted
text is handled, what the deployment does and doesn't harden, and how we check our own
work.

Every claim links to the code that backs it, so a developer can check the explanation
against reality.

---

## Table of contents

- [How security is managed here — the overview](#how-security-is-managed-here--the-overview)
  - [Table of contents](#table-of-contents)
  - [1. The short version](#1-the-short-version)
  - [2. What we're actually protecting](#2-what-were-actually-protecting)
  - [3. The three documented layers](#3-the-three-documented-layers)
  - [4. Tenancy — keeping users apart](#4-tenancy--keeping-users-apart)
  - [5. Handling text we didn't write](#5-handling-text-we-didnt-write)
  - [6. Rate limiting — the cost ceiling](#6-rate-limiting--the-cost-ceiling)
  - [7. The network edge](#7-the-network-edge)
  - [8. The deployment](#8-the-deployment)
  - [9. Checking our own work](#9-checking-our-own-work)
  - [10. Where the code lives](#10-where-the-code-lives)
  - [11. What this protects against — and what it doesn't](#11-what-this-protects-against--and-what-it-doesnt)
    - [Gaps recorded elsewhere](#gaps-recorded-elsewhere)
    - [Gaps with no other home](#gaps-with-no-other-home)

---

## 1. The short version

There is no single wall around this application. There are several thin ones, each doing
one job, arranged so that getting past one doesn't get you past the next.

| Layer | The job it does | Where it's explained |
|---|---|---|
| **Identity** | Prove you are who you say, without us ever storing your password | [password-hashing.md](./password-hashing.md) |
| **Session** | Remember that proof on every later click, unforgeably | [jwt.md](./jwt.md) |
| **Tenancy** | Point every database read at *your* data and nobody else's | §4 — here |
| **Secrets at rest** | Make a stolen database file useless without a separate key | [llm-keys.md](./llm-keys.md) |
| **Spend control** | Cap what a leaked credential can cost | [llm-keys.md](./llm-keys.md) |
| **Untrusted text** | Never let model output or config data become code | §5 — here |
| **Abuse limits** | Stop one account burning everyone's budget | §6 — here |
| **The edge** | TLS, no cross-origin access, nothing exposed that needn't be | §7, §8 — here |

The layers this document owns outright are §4, §5, §6, §7, §8 and §9. The rest are
summarised in §3 and explained properly in their own documents.

## 2. What we're actually protecting

Three things, and they need three different tools. This table appears in
[jwt.md](./jwt.md) and [llm-keys.md](./llm-keys.md) too, because confusing these three
guarantees is the classic mistake:

| Tool | Used for | Guarantee |
|---|---|---|
| **bcrypt** hashing | Passwords ([password-hashing.md](./password-hashing.md)) | One-way. Nothing can read it back, by design. |
| **Fernet** encryption | Stored LLM API keys ([llm-keys.md](./llm-keys.md)) | Reversible, deliberately — the app must read the key back to call the provider. |
| **RS256** signing + **ECDH-ES+A256KW** encryption | Session tokens ([jwt.md](./jwt.md)) | Both, stacked: the signature makes the token forgeable by nobody, the encryption makes it readable only by `BackEnd`. |

A fourth asset has no cryptography protecting it and doesn't need any: **your content** —
projects, surveys, generated posts. It's protected by being in a file nobody else's
requests can open, which is §4.

## 3. The three documented layers

Short pointers only. Each of these has a full document, and this page does not restate
them.

**Identity — [password-hashing.md](./password-hashing.md).** Passwords are hashed with
bcrypt at cost factor 12 and never stored in recoverable form. Login and registration
return the same message for an unknown user and a wrong password, so the endpoint can't
be used to discover which accounts exist.

**Session — [jwt.md](./jwt.md).** After login you carry a signed, self-contained,
24-hour token. `Web` holds the private key and mints tokens; `BackEnd` holds only the
public key and can verify them while being permanently incapable of creating one.

**Stored credentials and spend — [llm-keys.md](./llm-keys.md).** LLM API keys are
Fernet-encrypted in your own database file, masked before they're ever shown to a human,
and in production replaced entirely by a Bifrost virtual key: budget-capped, scoped to one
model, and worthless outside our own gateway.

## 4. Tenancy — keeping users apart

This is the layer with no document of its own, and it's the one most worth understanding,
because it works differently from how most applications do it.

**Every user has their own database file.** Not a shared table with a `user_id` column —
an actual separate SQLite file at `db/users/<user_id>.sqlite`. Isolation is therefore
enforced by *which file gets opened*, not by remembering to write `WHERE user_id = ?` on
every query. There is no query in the codebase that could forget the filter, because
there is no filter.

Two pieces make that work.

**The path, which is guarded three times.**
[`get_user_db_path()`](../BackEnd/src/db_manager.py#L15-L36) turns a user id into a
filename, and it is deliberately paranoid about it. First it rejects an empty id
([:17-18](../BackEnd/src/db_manager.py#L17-L18)). Then it strips path separators, `..`
and null bytes — and requires the stripped result to be **identical** to the input
([:22-26](../BackEnd/src/db_manager.py#L22-L26)):

```python
sanitized_user_id = user_id.replace('/', '').replace('\\', '').replace('..', '').replace('\0', '')

if not sanitized_user_id or sanitized_user_id != user_id:
    raise ValueError(...)
```

That "identical" check is the important part. A sanitiser that quietly *fixes* bad input
is how traversal bugs survive — the caller never learns anything was wrong. Here, any
stripping at all is a hard rejection. Then a third check requires the id to match
`^[a-zA-Z0-9_-]+$` ([:29-31](../BackEnd/src/db_manager.py#L29-L31)), which a UUID does
and an attack string doesn't.

**The current user, which comes only from a verified token.** Which file to open is held
in a `ContextVar` ([db_manager.py:9](../BackEnd/src/db_manager.py#L9)) — a variable scoped
to one request, so concurrent requests can't see each other's. The only place in the
application that writes it is
[`ensure_user_context`](../BackEnd/src/main.py#L116-L125):

```python
async def ensure_user_context(user_id: str = Depends(get_current_user_from_token)):
    set_current_user(user_id)
    # Verify the context was set properly
    current = get_current_user()
    if current != user_id:
        raise HTTPException(status_code=500, detail="Failed to set user context")
```

The id can only have come from a signature-checked JWT, and the function reads the value
back and refuses to continue if it doesn't match. If the context can't be trusted, the
request fails rather than proceeding against an unknown database.

Nothing falls back to a default, either:
[`get_current_user_db_path()`](../BackEnd/src/db_manager.py#L46-L51) raises if no user is
set, so an unauthenticated code path can't silently land on a shared file.

**47 of the 49 routes** in [`BackEnd/src/main.py`](../BackEnd/src/main.py) declare
`Depends(ensure_user_context)`. The only two that don't are
[`/api/register-user`](../BackEnd/src/main.py#L414-L418) and
[`/api/login-user`](../BackEnd/src/main.py#L420-L428) — which is how you get a token in
the first place. Both are rate-limited (5/hour, 10/minute) because anyone can reach them.

A third, `/api/current-user`, used to sit unauthenticated alongside them; it has been
deleted, since authenticating it would only have made it echo back the caller's own id.
[`tests/test_route_auth.py`](../BackEnd/tests/test_route_auth.py) now walks the route
table and fails if any `/api/` path lacks the dependency and is not one of those two —
which converts the warning below from a convention into a check.

> **The trade-off, stated plainly.** Because the whole scheme rests on that one
> dependency, `ensure_user_context` is a single point of failure for all tenancy. It is
> applied per-route rather than to the router as a whole, which means **a new route added
> without it is public and untenanted by default** — exactly the shape of the three
> exceptions above. That is the cost of the design; the benefit is that no individual
> query can leak across users by forgetting a `WHERE` clause.

Some history is preserved in the source as a comment at
[main.py:430-441](../BackEnd/src/main.py#L430-L441): three administrative endpoints —
including one that could set the current user to anyone — were removed for being
unauthenticated. `recreate_users_table()` was deleted outright, because dropping the
users table reissues every id and orphans every `db/users/<user_id>.sqlite` file named
after the old ones.

## 5. Handling text we didn't write

Three kinds of text arrive that we didn't author: what users type, what operators put in
config files, and what a language model generates. Each has a control.

**SQL — values are never concatenated.** Every query binds its values as parameters. The
only thing ever interpolated into a statement string is a *table name*, because SQLite
cannot parameterise identifiers — and that goes through one helper,
[`quote_identifier()`](../BackEnd/src/sql_identifiers.py#L23-L31), which validates against
a fixed nine-name set
([`ALLOWED_TABLES`](../BackEnd/src/sql_identifiers.py#L10)) and raises on anything else.
The module docstring states the rule
([:1-7](../BackEnd/src/sql_identifiers.py#L1-L7)): the interpolated value is "provably one
of a fixed set of names rather than whatever the caller happened to pass."

**File paths — reads stay inside the config root.**
[`resolve_within()`](../BackEnd/src/safe_paths.py#L12-L25) resolves both the root and the
candidate with `realpath` and rejects anything that doesn't land underneath:

```python
if candidate != resolved_root and not candidate.startswith(resolved_root + os.sep):
    raise ValueError(f"Path {filename!r} resolves outside of {root!r}")
```

Resolving first is what makes it catch symlinks pointing out of the directory, not just
`..` in the filename. The config root is operator-controlled rather than
request-controlled ([:1-7](../BackEnd/src/safe_paths.py#L1-L7)), so this is
defence in depth rather than the front line.

**Model output — an allowlist, enforced on display.** This one is worth reading the
reasoning for.
[`Web/src/locol-lib/htmlSanitize.py`](../Web/src/locol-lib/htmlSanitize.py) exists because
generated content is rendered as formatted HTML. The system prompt *asks* the model for a
small set of tags — and the docstring is blunt about why that isn't enough
([:4-10](../Web/src/locol-lib/htmlSanitize.py#L4-L10)):

> A prompt is a request, not a guarantee - and prompt templates are user-editable in
> Settings, so the system prompt itself can be replaced. This module enforces that
> same tag contract on the display side, so rendering the content formatted doesn't
> mean trusting the model with the browser.

So the display side re-enforces it independently: thirteen allowed tags
([:19-21](../Web/src/locol-lib/htmlSanitize.py#L19-L21)); `script` and `style` have their
*contents* dropped rather than kept as text
([:27](../Web/src/locol-lib/htmlSanitize.py#L27)); links keep only `href` and `title`, and
only for `http://`, `https://` or `mailto:` schemes, which is what blocks `javascript:`
([:31](../Web/src/locol-lib/htmlSanitize.py#L31),
[:47-60](../Web/src/locol-lib/htmlSanitize.py#L47-L60)); and every link gets
`rel="noopener noreferrer"` forced on. It's all stdlib — no sanitiser dependency to keep
patched.

**Prompt injection is not solved, and isn't claimed to be.** User-supplied voice text is
appended to the system prompt with a natural-language instruction not to override the
task — a request, not an enforceable control — and scraped third-party web content is fed
into prompts as-is. The honest position is that the *output* side is the backstop: the
sanitiser above assumes the model may have been talked into emitting anything.

## 6. Rate limiting — the cost ceiling

Eight of the fifty routes carry a limit. Six are the endpoints that reach an LLM and
therefore spend real money; two are the unauthenticated auth endpoints.

The interesting design choice is *what the limit counts against*. For the spending
endpoints it's the authenticated user, not the IP address
([`_user_rate_limit_key()`](../BackEnd/src/main.py#L81-L88)) — the comment explains that
colleagues behind one office NAT would otherwise eat each other's budget. The full
reasoning is in [jwt.md §8](./jwt.md#8-a-second-job--fair-rate-limiting) and isn't
repeated here.

| Limit | Applies to | Keyed by |
|---|---|---|
| 20/minute | The five interactive LLM endpoints | User |
| 5/minute | `/api/generate-project-items`, which fans out to one call per idea | User |
| 5/hour | `/api/register-user` | IP |
| 10/minute | `/api/login-user` | IP |

The two IP-keyed limits have to be IP-keyed — there's no authenticated user yet. The
login limit is the control against online password guessing, on top of bcrypt's
deliberate slowness.

## 7. The network edge

**No cross-origin browser access by default.** `LOCOL_CORS_ALLOW_ORIGINS` is empty unless
an operator sets it, which makes the CORS middleware effectively inert
([main.py:59-70](../BackEnd/src/main.py#L59-L70)). The rationale at
[:54-58](../BackEnd/src/main.py#L54-L58) is worth knowing: nothing needs it, because the
Content Editor is served from `/www` by the same app, and `Web` talks to the API
server-side with `requests`, where CORS never applies.

In Kubernetes that empty default is the shipped state on both sides: the key is present
but commented out in [01-configmap.yaml:92-103](../k8s/01-configmap.yaml#L92-L103), and
[03-deployment.yaml:134-146](../k8s/03-deployment.yaml#L134-L146) reads it as an
`optional` ConfigMap key so an unset key leaves the allowlist empty rather than blocking
startup. Widening it takes a deliberate edit in both files, which is the intent — see the
CSRF note below for what an empty allowlist is holding up.

**TLS terminates at the ingress.** cert-manager issues the certificate, and both
`ssl-redirect` and `force-ssl-redirect` are on, so plain HTTP is redirected rather than
served ([k8s/05-ingress.yaml:16-18](../k8s/05-ingress.yaml#L16-L18),
[:28-31](../k8s/05-ingress.yaml#L28-L31)). Application code does not enforce TLS — it is a
deployment property, which is why both [jwt.md](./jwt.md) and
[password-hashing.md](./password-hashing.md) say the password and the bearer token are
only protected in transit if the deployment is doing its job.

**Nothing is exposed that needn't be.** Both Services are `ClusterIP`; the only way in
from outside is the Ingress, which routes just three paths. Bifrost has no Ingress at
all — reaching its admin UI requires `kubectl port-forward`.

**There is no CSRF token anywhere, and the design doesn't currently need one.** Worth
stating explicitly rather than leaving as an apparent omission: authentication is a
bearer *header*, not an ambient cookie, so a cross-site form post carries no credentials;
no origins are allowed by CORS; and the editor's cookie is `SameSite=Strict` and is only
ever read by JavaScript to build that header. Each of those three is load-bearing — change
one and CSRF becomes a live question.

## 8. The deployment

Key material never sits in an environment variable. The two Secrets holding keys are
mounted as **read-only volumes** and the app is told only where to look
([03-deployment.yaml:200-233](../k8s/03-deployment.yaml#L200-L233)):

| Secret | Holds | Mounted at |
|---|---|---|
| `locol-ai-jwt-keys` | `private_key.pem`, `public_key.pem`, `enc_private_key.pem`, `enc_public_key.pem` | `/keys`, read-only |
| `locol-ai-db-key` | `db_encryption.key` | `/db-key`, read-only |
| `locol-ai-secrets` | `SERPER_API_KEY`, `LOCOL_BIFROST_ADMIN_TOKEN` — both optional | env |
| `bifrost-secrets` | The real provider API keys | Bifrost pod only |

That last row is the point of the Bifrost design: the credential that can actually spend
money exists only inside the gateway pod, never in the app and never in a user's database.
See [llm-keys.md §8](./llm-keys.md#8-what-a-virtual-key-actually-is).

All user data lives on one `ReadWriteOnce` PVC, `locol-ai-storage`, mounted at
`/app/BackEnd/db` ([02-storage.yaml](../k8s/02-storage.yaml)). That volume holds both the
shared users table — usernames, emails, bcrypt hashes — and every per-user database with
its encrypted API keys. **The encryption key must not be backed up alongside it**; the two
together give up everything ([llm-keys.md §14](./llm-keys.md#14-what-this-protects-against--and-what-it-doesnt)).

**Nothing in the pod runs as root.** The image drops to an unprivileged `app` user
(UID 1000) as its last build step ([Dockerfile:85](../Dockerfile#L85)), so supervisord and
all three processes it starts — BackEnd, Web and sqlite-web — run unprivileged; there is no
`user=` directive left in [supervisord.conf](../supervisord.conf) to undo that. Both
Deployments back it with a `securityContext`
([03-deployment.yaml:37-64](../k8s/03-deployment.yaml#L37-L64)): `runAsNonRoot` makes the
kubelet refuse a pod whose image ever regresses to root, `allowPrivilegeEscalation: false`
and `capabilities: drop: [ALL]` remove the ways a compromised process would climb back up,
and `fsGroup: 1000` is what makes the user-data PVC writable by that UID at all. This is the
same set [`bifrost/k8s/02-deployment.yaml`](../bifrost/k8s/02-deployment.yaml) uses, applied
now to both pods rather than one.

Operator procedure isn't duplicated here. Generating the keys and creating the secrets is
[deploy-k8s.md §4](./deploy-k8s.md#4-generate-keys-create-secrets-and-the-question-sets-configmap), which also covers
the fact that Kubernetes Secrets are base64-encoded rather than encrypted and what to do
about that. The production checklist is
[deploy-k8s.md §11](./deploy-k8s.md#11-production-and-security-notes). What the key files
are and why one of them is not disposable is
[deploy-local.md §4.1](./deploy-local.md#41-the-keys-it-generates).

> **The manifests in [`k8s/`](../k8s/) are templates, not necessarily what is running.**
> A deployment's real, environment-specific manifests live outside version control, and
> can override any of the settings described above — including the security-relevant ones.
> Reviewing the deployed configuration against these templates is a separate exercise from
> reading this document, and a worthwhile one.

## 9. Checking our own work

The repo runs [Bearer](https://docs.bearer.com/), a static analysis scanner, over
first-party source. This is undocumented anywhere else, so it's recorded here.

[`bearer.yml`](../bearer.yml) scopes the scan. Without it, a root scan reports around 1400
findings, roughly 1300 of them inside `BackEnd/.venv`
([:5-11](../bearer.yml#L5-L11)) — dependency source this repo doesn't author and can't
patch in place. Build output is excluded for the same reason: the defect, if any, lives in
the source it was generated from. The config is committed rather than living in
remembered CLI flags so that "every operator — and any future CI job — scans exactly the
same tree" ([:13-14](../bearer.yml#L13-L14)).

[`bearer.ignore`](../bearer.ignore) holds 27 suppressed findings — and it is a *triage
record*, not a mute button. Every entry names an author, a date, and a justification. They
fall into four groups, and the justifications are checkable: SQL identifier interpolation
(safe because of `quote_identifier`, §5), path traversal in YAML config loading (safe
because of `safe_paths`, §5), the containment guards themselves being flagged, and two DOM
false positives.

Run it with [`scripts/run-bearer-scan.sh`](../scripts/run-bearer-scan.sh) or the `.ps1`
equivalent. All four severities are enabled by default, and the report is written to
`bearer.log`, which is gitignored while the config and the ignore file are committed.

> **This is the whole of the automated checking, and it is manual.** The scan runs when
> someone runs it. There is **no CI pipeline**, no dependency vulnerability audit, no
> secret scanning, and no automated dependency updates. `run-bearer-scan.sh` has a
> `--fail` flag that exits non-zero on any finding — the hook a CI job would use — but
> nothing invokes it. Dependencies are declared with `>=` floors rather than pins, with
> `uv.lock` files committed, so reproducibility depends on installs honouring the
> lockfile.

## 10. Where the code lives

| Concern | Location |
|---|---|
| Setting the user context | [`ensure_user_context`](../BackEnd/src/main.py#L116-L125) — main.py:116-125 |
| Deriving a user's database path | [`get_user_db_path`](../BackEnd/src/db_manager.py#L15-L36) — db_manager.py:15-36 |
| Refusing to guess a database | [`get_current_user_db_path`](../BackEnd/src/db_manager.py#L46-L51) — db_manager.py:46-51 |
| SQL identifier allowlist | [`quote_identifier`](../BackEnd/src/sql_identifiers.py#L23-L31) — sql_identifiers.py:23-31 |
| Path containment | [`resolve_within`](../BackEnd/src/safe_paths.py#L12-L25) — safe_paths.py:12-25 |
| HTML sanitising | [htmlSanitize.py](../Web/src/locol-lib/htmlSanitize.py) |
| Rate-limit keys | [`_rate_limit_key`](../BackEnd/src/main.py#L72-L79) / [`_user_rate_limit_key`](../BackEnd/src/main.py#L81-L88) |
| CORS configuration | [main.py:59-70](../BackEnd/src/main.py#L59-L70), wired in at [k8s/01-configmap.yaml:92-103](../k8s/01-configmap.yaml#L92-L103) / [03-deployment.yaml:134-146](../k8s/03-deployment.yaml#L134-L146) |
| TLS and routing | [k8s/05-ingress.yaml](../k8s/05-ingress.yaml) |
| Secret mounts | [k8s/03-deployment.yaml:200-233](../k8s/03-deployment.yaml#L200-L233) |
| Static analysis config | [bearer.yml](../bearer.yml), [bearer.ignore](../bearer.ignore) |

## 11. What this protects against — and what it doesn't

**A stolen database file is not a breach of passwords.** Usernames and 60-character
bcrypt strings, with no way back to the passwords themselves.

**A stolen database file is not a breach of API keys either** — not without the separate
encryption key, which lives in a different Kubernetes Secret.

**One user cannot read another's content.** Not because a query filters correctly, but
because the file is never opened.

**A forged session is not possible.** Minting a token requires a private key that only
`Web` holds.

**What is not defended:** anything that follows from an attacker holding both a database
file *and* the encryption key; anything that follows from a token being copied while
still valid; and anything in transit if the deployment isn't terminating TLS.

### Gaps recorded elsewhere

Each control's own document is the authoritative record of its limits, and this page does
not copy them — a second copy only drifts out of date. Read them there:

| Area | Its limits are recorded in |
|---|---|
| Passwords | [password-hashing.md §6](./password-hashing.md#6-what-this-protects-against--and-what-it-doesnt) |
| Session tokens | [jwt.md §11](./jwt.md#11-what-this-protects-against--and-what-it-doesnt) |
| Stored credentials and spend | [llm-keys.md §14](./llm-keys.md#14-what-this-protects-against--and-what-it-doesnt) |
| The browser editor | [content-editor-flow.md §Findings](./content-editor-flow.md#findings) |

### Gaps with no other home

These are recorded here because no other document covers them. "Accepted residual risk"
is used in the same sense as elsewhere in these docs: known, deliberate or tolerated, and
written down rather than forgotten.

> **The SQLite admin UI runs unauthenticated in every container.**
> [supervisord.conf:38-50](../supervisord.conf#L38-L50) starts `sqlite-web` against the
> shared users database — which holds every username, email and password hash — bound to
> `0.0.0.0` with `autostart=true` and no password, though the tool supports one. It is
> deliberately left out of the published Service
> ([k8s/04-service.yaml](../k8s/04-service.yaml)) and has no Ingress, so it is not
> internet-reachable in the shipped configuration, and
> [deploy-k8s.md §11](./deploy-k8s.md#11-production-and-security-notes) says never to
> expose it. But nothing stops a Service or a manifest override from publishing it, and
> with **no NetworkPolicy anywhere in the repo**, anything already inside the cluster
> network can reach it.
>
> It does *not* run as root — see [§8](#8-the-deployment) — so what it can reach is the
> database files, which is quite enough.
>
> **The container's root filesystem is writable.** `readOnlyRootFilesystem` is the one
> item of the standard hardening set left unset on both Deployments. `uv run` resolves the
> virtualenv at start-up, Streamlit writes under `$HOME` and supervisord writes a pidfile,
> so turning it on requires `emptyDir` mounts over `/tmp` and `/home/app` — a change with
> its own failure modes, deliberately kept separate from dropping to a non-root user.
> Everything else in that set *is* applied ([§8](#8-the-deployment)): non-root UID,
> `runAsNonRoot`, no privilege escalation, all capabilities dropped. Accepted residual risk.
>
> **The production command runs uvicorn with the reloader on.**
> [main.py:454](../BackEnd/src/main.py#L454) passes `reload=True`, and that is the exact
> line supervisord runs in the container. The reloader is a development tool: it watches
> the filesystem and runs an extra supervising process.
>
> **The user-facing app has no liveness or readiness probes.** A process that hangs rather
> than exits keeps receiving traffic and is never restarted —
> `autorestart=true` only covers a process that actually dies. Bifrost has both probes;
> the app has neither.
>
> **No security response headers.** No CSP, HSTS, `X-Content-Type-Options`,
> `X-Frame-Options` or `Referrer-Policy` is set anywhere
> ([main.py:52](../BackEnd/src/main.py#L52)). The missing CSP matters most, because it is
> what would blunt an XSS that reached the Content Editor, whose session cookie is
> necessarily script-readable
> ([content-editor-flow.md §1](./content-editor-flow.md#1-the-session-cookie-is-script-readable)).
>
> **The API documentation is public.** `FastAPI()` is constructed with defaults
> ([main.py:52](../BackEnd/src/main.py#L52)), so `/docs`, `/redoc` and `/openapi.json` are
> served unauthenticated and enumerate all fifty routes with their schemas.
>
> **Prompt and response text is printed to standard output on every call.**
> [llm.py:403](../BackEnd/src/llm.py#L403) and [:411](../BackEnd/src/llm.py#L411) log the
> first 500 characters of each prompt and each model response. This is *not* gated by
> `DEBUG` — it happens regardless — so user content reaches the container logs, which have
> no rotation, no redaction and no stated retention.
>
> **The two unauthenticated auth endpoints return raw exception text.**
> [user_management.py:109](../BackEnd/src/user_management.py#L109) and
> [:176](../BackEnd/src/user_management.py#L176) put `str(e)` in the response body, so a
> database error could surface schema or path detail to an unauthenticated caller. Note
> this is separate from the login flow's message handling, which correctly returns an
> identical message for unknown-user and wrong-password.
>
> **Almost nothing bounds request size.** The only length constraint on any field in the
> application is `max_length=25` on a batch's selected ideas
> ([generate_items_models.py:31-35](../BackEnd/src/generate_items_models.py#L31-L35)).
> Every other string — content, queries, prompt templates, voice text, registration
> fields — is an unconstrained `str`, and there is no body-size limit at the ASGI layer.
>
> **Authentication is opt-in per route.** As §4 sets out, `Depends(ensure_user_context)`
> is applied route by route rather than to the router, so a new endpoint is public and
> untenanted unless its author remembers. The two current exceptions are exactly that
> shape.
>
> **Registration discloses whether a username is taken.** Necessary for a usable signup
> form, and rate-limited to 5/hour per IP, but it is an account-enumeration oracle that
> the login endpoint deliberately avoids being.

One thing that is *not* a gap, recorded because it looks like one: the unsanitised
`innerHTML` in
[`quill-view-html.tsx`](../FrontEnd/src/components/quill-view-html/quill-view-html.tsx#L23)
is unused vendored code from the upstream stencil-quill project. The Content Editor uses
`<quill-view format="json">` ([index.html:159](../FrontEnd/src/index.html#L159)), which
routes content through Quill's Delta API
([quill-view.tsx:37-42](../FrontEnd/src/components/quill-view/quill-view.tsx#L37-L42)) and
never assigns HTML.
