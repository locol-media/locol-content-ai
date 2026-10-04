# Deploying Locol Content AI to Kubernetes

This guide walks through deploying Locol Content AI to any Kubernetes cluster, with
specific notes for **Amazon EKS** and **DigitalOcean Kubernetes (DOKS)**. The
parameterized manifests in [`../k8s/`](../k8s/) are the starting point; you fill
in a few placeholders and apply them.

> The maintainer's real, environment-specific manifests live in a gitignored
> `local/` folder and are not part of this repo. Treat `k8s/` as a template.

## 1. Architecture recap

The whole app ships as **one container image** (built from the repo-root
`Dockerfile`). Inside it, `supervisord` runs three processes:

| Process | Default port | Purpose |
|---|---|---|
| BackEnd (FastAPI) | 8000 | API for both UIs; serves the Content Editor at `/www`. |
| Web (Streamlit) | 8501 | Main user-facing app (login, surveys, brainstorming). |
| sqlite-web | 8080 | DB admin UI — **internal only, never exposed publicly**. |

Each port comes from an env var (`LOCOL_BACKEND_PORT`, `LOCOL_WEB_PORT`,
`LOCOL_SQLITE_WEB_PORT`) whose default is baked into the image, so the table above
holds unless you set the matching key in `01-configmap.yaml`. If you do, change the
matching `containerPort` in `03-deployment.yaml` to the same number — the Service and
Ingress address those ports **by name**, so neither needs editing. Don't delete the
ConfigMap keys: supervisord expands the variables at startup and won't start if one
resolves to nothing (the image's own defaults cover an unset key, which is why the
Deployment marks them `optional: true`).

All three run as the unprivileged `app` user (UID 1000) — the image ends with
`USER app`, and the Deployment asserts `runAsNonRoot` so the kubelet refuses to start
a pod whose image regressed to root. See section 11.

A single `Deployment` (1 replica) runs the image. The only persistent state is
per-user SQLite databases under `/app/BackEnd/db`, backed by one ReadWriteOnce
PVC. An Ingress routes `/api` and `/www` to the BackEnd and everything else to the
Streamlit UI.

The manifests in `k8s/` are numbered for apply order:

| File | Object |
|---|---|
| `00-namespace.yaml` | `locol-ai` namespace |
| `01-configmap.yaml` | `locol-ai-config` (env vars) |
| `02-storage.yaml` | `locol-ai-storage` PVC (per-user DBs) |
| `03-deployment.yaml` | the Deployment |
| `04-service.yaml` | `locol-ai-service` (ClusterIP, ports 8000/8501 → the named container ports) |
| `05-ingress.yaml` | Ingress (TLS via cert-manager) |

Four objects the Deployment depends on are **not** in `k8s/` — the three secrets and
the `question-sets-config` ConfigMap that carries the survey content. They hold data
that either must not be committed or lives elsewhere in the repo, so section 4
creates them imperatively. Do that before applying `k8s/`.

## 2. Prerequisites

- A Kubernetes cluster and `kubectl` configured for it.
- An [ingress-nginx](https://kubernetes.github.io/ingress-nginx/) controller
  (or, on EKS, the AWS Load Balancer Controller — see the [EKS appendix](#eks-appendix)).
- [cert-manager](https://cert-manager.io/) installed, with a `ClusterIssuer`
  named `letsencrypt-prod` (or edit the name in `05-ingress.yaml`).
- A container registry you can push to (ECR, DOCR, GHCR, Docker Hub, …).
- Control over a DNS name to point at the ingress load balancer.

## 3. Get the image

### Option A — pull the published image (recommended)

Every GitHub Release publishes a prebuilt image to GitHub Container Registry, so
there is nothing to build:

```
ghcr.io/locol-media/locol-content-ai:0.2.0   # immutable - use this in production
ghcr.io/locol-media/locol-content-ai:latest  # newest release; moves
ghcr.io/locol-media/locol-content-ai:edge    # newest commit on main; moves
```

`k8s/03-deployment.yaml` already points at `:latest`. Change it to a version tag for
anything you care about keeping reproducible — `:latest` and `:edge` both move under
you, and the Deployment sets `imagePullPolicy: Always`, so a restart is enough to
pick up a different image. See [release.md](release.md) for the full tag scheme and
how releases are cut.

If the package is **public**, no pull secret is needed and you can skip to section 4.
If it is **private**, see [image pull secret](#image-pull-secret-private-registries)
below.

### Option B — build and push to your own registry

Needed if you've made local changes, or if your cluster must pull from a registry
inside your own account. From the repo root:

```bash
docker build -t locol-ai:latest .
```

Then tag and push to your registry.

**Amazon ECR:**

```bash
aws ecr create-repository --repository-name locol-ai   # once
aws ecr get-login-password --region <region> \
  | docker login --username AWS --password-stdin <acct>.dkr.ecr.<region>.amazonaws.com
docker tag locol-ai:latest <acct>.dkr.ecr.<region>.amazonaws.com/locol-ai:latest
docker push <acct>.dkr.ecr.<region>.amazonaws.com/locol-ai:latest
```

**DigitalOcean Container Registry:**

```bash
doctl registry login
docker tag locol-ai:latest registry.digitalocean.com/<your-registry>/locol-ai:latest
docker push registry.digitalocean.com/<your-registry>/locol-ai:latest
```

Set the pushed image reference in `k8s/03-deployment.yaml` (`image:`).

### Image pull secret (private registries)

- **GHCR:** only needed if the package visibility is Private. Create a classic PAT
  with the `read:packages` scope, then:

  ```bash
  kubectl create secret docker-registry registry-credentials \
    --namespace locol-ai \
    --docker-server=ghcr.io \
    --docker-username=<github-username> \
    --docker-password=<PAT with read:packages>
  ```

  Then uncomment the `imagePullSecrets` stub in `03-deployment.yaml`. Making the
  package public avoids all of this.
- **ECR:** nodes with an appropriate IAM role can pull from ECR without a pull
  secret. Otherwise create a `docker-registry` secret from an `aws ecr
  get-login-password` token.
- **DOCR:** `doctl registry kubernetes-manifest | kubectl apply -f -` creates a
  pull secret; add it under `imagePullSecrets` in the Deployment (there's a
  commented stub there).

## 4. Generate keys, create secrets and the question-sets ConfigMap

The app needs two JWT key pairs — an RSA pair for signing/verification and an EC
P-256 pair for encrypting the token — plus a Fernet key (encrypting stored LLM API
keys). Generate them locally — no Python or `uv` needed, just PowerShell (Windows)
or `openssl` (macOS/Linux):

```powershell
./scripts/generate-jwt-keys.ps1
./scripts/generate-db-encryption-key.ps1
```
```bash
./scripts/generate-jwt-keys.sh
./scripts/generate-db-encryption-key.sh
```

This writes `keys/private_key.pem`, `keys/public_key.pem`,
`keys/enc_private_key.pem`, `keys/enc_public_key.pem`, and
`keys/db_encryption.key` (the `keys/` directory is gitignored). See
[jwt.md](jwt.md) for which service uses which half.

> **Warning:** keep `db_encryption.key` safe and stable. It decrypts the LLM API
> keys stored in the per-user databases — if you lose or regenerate it after data
> has been saved, those stored keys become permanently unrecoverable.

> **Nothing is generated for you in-cluster, by design.** The image's entrypoint
> ([`scripts/docker-entrypoint.sh`](../scripts/docker-entrypoint.sh)) *can* create these
> five files and the accounts database, which is how the single-host compose deployment
> works ([deploy-compose.md §4](deploy-compose.md#4-what-the-first-start-creates)) — but
> only when `LOCOL_BOOTSTRAP` is set, and this deployment deliberately never sets it.
>
> That is not a limitation to work around. A key generated inside a pod lives on the
> container filesystem: it disappears on the next restart, logging every user out, and
> if it were `db_encryption.key` it would take every stored LLM API key with it. The
> keys belong in Secrets and the database on the PVC, provisioned here, where they
> outlive any pod.
>
> On start the entrypoint reports what it found and starts the services either way, so a
> Secret that is missing or incomplete still surfaces the way the rest of this section
> describes — as a 500 naming the unreadable path — rather than as a CrashLoopBackOff.

Create the namespace first, then the secrets in it:

```bash
kubectl apply -f k8s/00-namespace.yaml

# Piped through `apply` rather than a bare `create`, so this is idempotent - a bare
# `kubectl create secret` fails with AlreadyExists on a cluster that already has it,
# which is exactly the case when you are adding the two enc_* keys to an existing
# deployment. Same pattern as the question-sets ConfigMap below.
kubectl create secret generic locol-ai-jwt-keys --namespace locol-ai \
  --from-file=private_key.pem=./keys/private_key.pem \
  --from-file=public_key.pem=./keys/public_key.pem \
  --from-file=enc_private_key.pem=./keys/enc_private_key.pem \
  --from-file=enc_public_key.pem=./keys/enc_public_key.pem \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic locol-ai-db-key --namespace locol-ai \
  --from-file=db_encryption.key=./keys/db_encryption.key \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic locol-ai-secrets --namespace locol-ai \
  --from-literal=SERPER_API_KEY=<your-serper-api-key> \
  --dry-run=client -o yaml | kubectl apply -f -
```

> **Upgrading an existing deployment? Update this secret *before* rolling out the new
> image.** The session token is a signed JWT sealed in a JWE
> ([jwt.md](jwt.md)), so `BackEnd` needs `enc_private_key.pem` and `Web` needs
> `enc_public_key.pem`. Neither existed in deployments predating that change, and the
> secret is mounted as a whole directory — so applying the new manifests alone does
> **not** add them.
>
> Roll out the image first and every authenticated request returns **500**
> `Server authentication key is not configured`, with `[ERROR] JWT key configuration`
> in the pod log naming the missing path. The app will not limp along; it stops
> serving authenticated traffic entirely. Run the secret command above, confirm all
> four files are present (section 9), then `kubectl -n locol-ai rollout restart
> deploy/locol-ai`.
>
> Note that adding the EC pair invalidates nothing on its own, but generating a
> *fresh* RSA pair at the same time logs every user out. Reuse the existing
> `private_key.pem` / `public_key.pem` if you want the upgrade to be seamless —
> `generate-jwt-keys.sh` refuses to overwrite them without `--force`.

`SERPER_API_KEY` (a [Serper](https://serper.dev/) Google-search key) is **optional**.
It only fed the Reddit writing-style analyzer on the Find Your Voice page, which is
disabled because Reddit blocks the automated access it relied on — voices are written
by hand instead. The BackEnd deployment reads the key as an optional secret entry, so
you can create `locol-ai-secrets` without it (or omit the secret entirely if you are
not setting `LOCOL_BIFROST_ADMIN_TOKEN` either). To run the analyzer anyway, supply the
key and set `LOCOL_FIND_YOUR_VOICE_ENABLED=true` on **both** the BackEnd and Web
deployments.

> **Secure your secrets at rest.** By default, native Kubernetes Secrets are only
> Base64-encoded, **not encrypted** — anyone who can read them from the API or
> etcd can trivially decode them. Before storing real credentials here, make sure
> your cluster's secrets are actually secured: enable
> [encryption at rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
> (e.g. a KMS provider), lock down RBAC access to Secrets, and/or use an external
> secrets manager (AWS Secrets Manager, DigitalOcean, HashiCorp Vault, External
> Secrets Operator). This is especially important for `locol-ai-db-key`, which
> can decrypt every stored LLM API key.

### The question-sets ConfigMap

The Streamlit survey content lives in [`../Web/question-sets/`](../Web/question-sets/):
eight flat YAML files, about 15KB in total — four question sets (Business Survey,
Default Question Set, Tell your story, Generated Story) each paired with the page
layout named by its `page_configs_file` key. That is comfortably inside the 1MB
ConfigMap limit, so the whole directory goes in one ConfigMap:

```bash
kubectl create configmap question-sets-config --namespace locol-ai \
  --from-file=Web/question-sets/ --dry-run=client -o yaml | kubectl apply -f -
```

Run it from the repo root. Each file becomes a ConfigMap key named after its
basename, which is what makes the mounted directory look identical to the repo one.

**This step is required, not optional.** The files are baked into the image by the
`Dockerfile`'s `COPY Web/ ./Web/`, but `03-deployment.yaml` mounts this ConfigMap over
`/app/Web/question-sets` so the sets can be maintained without a rebuild. Skip it and
the pod sits in `ContainerCreating` with a `configmap "question-sets-config" not
found` event on `kubectl describe pod`.

**The mount replaces the whole directory** — it does not merge with the image's copy.
Always point `--from-file=` at the directory rather than listing individual files: a
partial ConfigMap makes the missing sets disappear from the survey picker with no
error in the logs, and a set whose `page_configs_file` is absent fails when a user
opens it. The app enumerates every `*.yaml`/`*.yml` in the directory and silently
skips any file without a top-level `name` key, which is why an incomplete ConfigMap
looks like nothing is wrong.

**To edit a question set:** change the file in `Web/question-sets/`, re-run the exact
command above (it is idempotent — the `--dry-run | apply` pipe updates an existing
ConfigMap in place), then restart the pod:

```bash
kubectl -n locol-ai rollout restart deploy/locol-ai
```

The restart is not optional either. The loaders in
[`projectState.py`](../Web/src/locol-lib/projectState.py#L32-L36) are `@st.cache_data`-cached
for the life of the process, so an updated ConfigMap on its own changes nothing a user
sees. (The kubelet also takes up to a minute to propagate the new contents into the
mounted volume.)

## 5. Configure the manifests

Edit the placeholders:

- `k8s/01-configmap.yaml` — set `LOCOL_API_URL` / `LOCOL_WWW_URL` to
  `https://<your-host>`. `LOCOL_LLM_REQUEST_TIMEOUT` (seconds the Web app waits
  on an LLM-backed request) defaults to `180`; if you raise it, raise the
  `proxy-read-timeout` / `proxy-send-timeout` annotations in `05-ingress.yaml`
  above it too, or nginx returns a 504 before the app can report the timeout.
  `LOCOL_BIFROST_ENABLED` ships as `"true"` and `LOCOL_BIFROST_URL` points at the
  Bifrost gateway (see below) — **set `LOCOL_BIFROST_ENABLED: "false"` if you
  aren't deploying Bifrost**; every user then keeps the provider key seeded from
  `llm.yaml`, and no other key needs changing.
  `LOCOL_CORS_ALLOW_ORIGINS` ships commented out, which leaves browser cross-origin
  access switched off — correct here, because the ingress puts the Content Editor at
  `/www` on the same host as `/api` and the Web app calls the API server-side, where
  CORS never applies. Only uncomment it (comma-separated origins) if you serve the
  editor from a different host than the API; the Deployment already reads the key as
  optional, so no manifest edit is needed. Read
  [security-management.md §7](./security-management.md#7-the-network-edge) before you
  widen it — the empty allowlist is one of three properties standing in for a CSRF
  token.
- `k8s/02-storage.yaml` — set `storageClassName` (see next section).
- `k8s/03-deployment.yaml` — set `image:` (and `imagePullSecrets` if needed).
- `k8s/05-ingress.yaml` — set `<YOUR_HOST>`; adjust the cert-manager issuer name
  if yours isn't `letsencrypt-prod`.

## 6. Choose a storage class

`02-storage.yaml` needs a **ReadWriteOnce block-storage** class (a single replica
mounts it):

| Platform | Storage class | Notes |
|---|---|---|
| Amazon EKS | `gp3` | Requires the EBS CSI driver add-on. |
| DigitalOcean | `do-block-storage` | Default DO block storage. |
| GKE | `premium-rwo` / `standard-rwo` | |
| kind / k3s / minikube | `standard` (or unset) | Uses the cluster default. |

Run `kubectl get storageclass` to see what's available in your cluster.

A freshly provisioned volume is root-owned, and the container runs as UID 1000, so
the Deployment's `fsGroup: 1000` is what makes it writable — don't remove it (section
11). The same setting relabels a volume that was written by an older, root-running
image, so **upgrading an existing cluster needs no manual `chown`**: the kubelet does
it on the next pod start. `fsGroupChangePolicy: OnRootMismatch` skips that walk once
the ownership already matches, so only the first start after the upgrade pays for it —
on a large volume that one start can take noticeably longer.

## 7. Apply the manifests

Section 4 first — the Deployment mounts the `question-sets-config` ConfigMap and reads
the secrets, so applying `k8s/` before they exist leaves the pod stuck in
`ContainerCreating`.

```bash
kubectl apply -f k8s/
```

The numbered filenames apply in the right order. Re-running is safe (idempotent).

### Optional: override the seed config without rebuilding

By default the channel/LLM/prompt-template seed data baked into the image
(`/app/BackEnd/config`) is used, so no extra volume is required. To customize it
without rebuilding, create a ConfigMap from your `config/` directory and mount it,
then point `LOCOL_CONFIG_LOCATION` at the mount path:

```bash
kubectl create configmap yaml-config --namespace locol-ai \
  --from-file=config/ --dry-run=client -o yaml | kubectl apply -f -
```

The Streamlit survey content works differently: its `question-sets-config` ConfigMap
is **not** optional and has no env-var switch — the Deployment always mounts it at
`/app/Web/question-sets`. It is created in [section 4](#4-generate-keys-create-secrets-and-the-question-sets-configmap),
which also covers editing a question set and rolling the change out.

### Optional: the Bifrost LLM gateway

`bifrost/k8s/` deploys [Bifrost](https://docs.getbifrost.ai/), an LLM gateway. With
it in place and `LOCOL_BIFROST_ENABLED: "true"` plus `LOCOL_BIFROST_URL` set in
`01-configmap.yaml`, registering a user also creates a Bifrost customer named after
them and a `<username>-key` virtual key hanging directly off it — and points their
default LLM at the gateway instead of straight at the provider. That gives per-user
attribution, budgets and rate limits at the gateway rather than a shared provider key
in `llm.yaml`.

Setting `LOCOL_BIFROST_ENABLED` to `"false"` (and restarting the pod, since env is
read at startup) stops *new* provisioning, but does **not** move anyone back: users
already holding a virtual key keep routing through the gateway, so don't tear Bifrost
down without first repointing those rows. If the key is missing from the ConfigMap
entirely, the BackEnd falls back to the old behaviour of treating a non-empty
`LOCOL_BIFROST_URL` as "on".

The row it fills in is the one named **`Locol AI Default`** in
`BackEnd/config/default/llms/llm.yaml`; that name is the marker the code looks for, so
if you override the seed config keep the name. Provisioning also runs on every
authenticated request, so users who registered before Bifrost was configured are picked
up automatically, and both the customer and the key are get-or-create — a row that lost
its key is repaired with the key the user already has rather than accumulating a new one.

`LOCOL_BIFROST_DEFAULT_MODEL` decides what the provisioned row points at, in Bifrost's
`provider/model` form. Each user's virtual key is **scoped to exactly that provider and
model** — Bifrost denies by default, so an unscoped key serves nothing — and Bifrost must
also have a provider entry for the provider it names, holding a working upstream key and
permitting that model, or every provisioned user's LLM fails on first use — see the setup
steps below. The BackEnd carries no default, so leaving this unset skips provisioning
rather than guessing a model.

Changing this later only affects users who register afterwards. An existing user keeps the
model on their row, and their key stays scoped to it; the provisioning pass widens a key
that doesn't cover its own row's model (which repairs keys issued before scoping existed)
but never re-points a working user at a different model.

Each key is created with the spend cap in `LOCOL_BIFROST_BUDGET_MAX_LIMIT` (dollars)
and `LOCOL_BIFROST_BUDGET_RESET_DURATION`, defaulting to **$5/month**. Clearing the
limit creates uncapped keys. Changing either value only affects users who register
afterwards — existing keys keep the budget they were created with, and have to be
changed in Bifrost itself.

Setting it up takes three steps, and **all three are required** — stopping after the
Secret is the most common mistake, because Bifrost does not discover providers from
environment variables (see the first bullet below).

**1. Deploy Bifrost and give it the upstream key.** The variable name must match what
you reference in step 3; `DEEPSEEK_API_KEY` matches the `deepseek` default in
`01-configmap.yaml`.

```bash
kubectl apply -f bifrost/k8s/     # fill in the <RWO_STORAGE_CLASS>/<BIFROST_VERSION> placeholders first
kubectl -n locol-ai create secret generic bifrost-secrets \
  --from-literal=DEEPSEEK_API_KEY=<your-key>
```

If `bifrost-secrets` already exists, patch it instead of recreating it, so you keep any
other provider keys it holds:

```bash
kubectl -n locol-ai patch secret bifrost-secrets \
  --type merge -p "{\"stringData\":{\"DEEPSEEK_API_KEY\":\"<your-key>\"}}"
```

**2. Restart Bifrost if it was already running.** `envFrom` is resolved when the pod
starts, so an existing pod never sees a Secret you just created or patched. The
Deployment uses `strategy: Recreate` (the RWO volume forbids two pods), so model calls
fail for a few seconds during the swap.

```bash
kubectl -n locol-ai rollout restart deploy/bifrost
kubectl -n locol-ai rollout status  deploy/bifrost
```

**3. Register the provider in the Bifrost admin UI.** The Service is ClusterIP-only, so
port-forward to reach it:

```bash
kubectl -n locol-ai port-forward svc/bifrost 8080:8080
```

At `http://localhost:8080`, go to **Model Providers → Configurations**, select the
provider named in the prefix of `LOCOL_BIFROST_DEFAULT_MODEL` (DeepSeek, for the
`deepseek/deepseek-v4-flash` in `01-configmap.yaml`), and add a key:

| Field | Value |
| --- | --- |
| Name | `deepseek-key-1` |
| Value | `env.DEEPSEEK_API_KEY` — this literal string, **not** the key itself |
| Models | `*` |
| Weight | `1.0` |

The `env.` prefix is what dereferences the Secret from step 1, and it keeps the
credential out of `config.db` on the PVC. Use the `*` wildcard for **Models** unless you
specifically want to restrict it: this list and the user's virtual key are two separate
allowlists and a call has to satisfy both, so a **Models** list narrower than
`LOCOL_BIFROST_DEFAULT_MODEL` is the commonest way to produce the "no keys found" error
below. This configuration lives in `config.db` on the
`bifrost-storage` PVC: it survives pod restarts, but not deleting the PVC.

#### Same thing via the API

Equivalent to the UI steps above, for scripting a cluster rebuild. Keep the port-forward
from step 3 running.

**This is two calls, not one.** Bifrost v1.5.0 moved keys out of the provider payload into
a dedicated resource, so on any v1.5+ release the widely-copied single-call form
(`{"provider": "deepseek", "keys": [...]}`) creates a provider with **no keys** — leaving
you with exactly the `no keys found for provider` error this section exists to prevent.
Create the provider first, then attach the key.

```bash
# 1. Create the provider. This payload takes no keys.
curl -sS -X POST http://localhost:8080/api/providers \
  -H 'Content-Type: application/json' \
  -d '{"provider":"deepseek"}'

# 2. Attach a key that references DEEPSEEK_API_KEY from bifrost-secrets.
curl -sS -X POST http://localhost:8080/api/providers/deepseek/keys \
  -H 'Content-Type: application/json' \
  -d '{
        "name": "deepseek-key-1",
        "value": "env.DEEPSEEK_API_KEY",
        "models": ["*"],
        "weight": 1.0,
        "enabled": true
      }'

# 3. Verify. The key should come back as an env reference, not a literal credential.
curl -sS http://localhost:8080/api/providers
curl -sS http://localhost:8080/api/providers/deepseek/keys
```

`value` takes the literal string `env.DEEPSEEK_API_KEY`, same as the **Value** field in the
UI table above. The field is formally an object (`{value, ref, type}` with `type` one of
`plain_text`, `env`, `vault`) but accepts a bare string on input.

Call 2 returns **404 provider not found** if you skip call 1. If the provider already
exists, call 1 returns a conflict — harmless, just go straight to call 2. No
`Authorization` header is needed unless you have put Bifrost behind a token (see
`LOCOL_BIFROST_ADMIN_TOKEN` at the end of this section), in which case add
`-H "Authorization: Bearer <token>"` to every call.

On Windows, run these from Git Bash, or use `curl.exe` explicitly — in PowerShell `curl`
is an alias for `Invoke-WebRequest` and takes different arguments.

Also worth knowing before you turn this on:

- **Bifrost needs its own upstream provider key, configured in two places.** A virtual
  key is only an authorization scope, and setting an environment variable alone does
  nothing. `bifrost-secrets` supplies the credential's *value*; the provider entry inside
  Bifrost (step 3, by UI or API) supplies the *reference* to it (`env.DEEPSEEK_API_KEY`)
  and the model allowlist. Miss either half and every provisioned user's LLM fails with
  `no keys found for provider: <provider> and model: <model>`.
- **Only new registrations are provisioned.** Existing users keep whatever is in
  their `llms` table, including any key they entered themselves.
- **Signups survive a Bifrost outage.** A failure is logged and the user keeps the
  seeded config — but they get no virtual key, and nothing retries later.

**Checking it fired.** Provisioning prints a `[Bifrost]` line to stdout on every
registration, whatever the outcome — including when it's turned off. If you register a
user and see nothing, the new code isn't running (stale image) rather than failing
silently:

```bash
kubectl -n locol-ai logs deploy/locol-ai | Select-String "\[Bifrost\]"
```

`LOCOL_BIFROST_URL is not set` means the env var didn't reach the container — check the
ConfigMap was applied before the pod started, and that the `env:` block is present in
the Deployment.

A successful `[Bifrost] provisioned …` line says nothing about whether the provider is
configured — provisioning and routing fail independently, and a user whose row was
provisioned perfectly still gets `no keys found for provider` if step 3 was skipped. When
a model call fails, check the gateway's own log rather than the app's:

```bash
kubectl -n locol-ai logs deploy/bifrost --tail=100
```

`no keys found for provider` means no key was selectable for the call. Either the provider
entry is missing, or its **Models** allowlist excludes the model being requested, or — if
`curl -sS http://localhost:8080/api/providers/<provider>/keys` shows a healthy enabled key
covering that model — the *virtual key* is the one excluding it, by carrying an empty or
absent `key_ids`. A 401 from the upstream instead means the value in `bifrost-secrets` is
wrong.

A 403 `provider_blocked` — `Provider '<provider>' is not allowed for this virtual key` —
is the other allowlist: the *key* doesn't permit the provider, which is unrelated to
whether the provider entry exists. Keys issued before the BackEnd scoped them carry no
provider at all, and Bifrost denies by default. Signing in repairs a key in that state, so
this should only ever be seen once per user; if it persists, read the key back and check
its `provider_configs` against `LOCOL_BIFROST_DEFAULT_MODEL`:

```bash
kubectl -n locol-ai port-forward svc/bifrost 8080:8080
curl -sS http://localhost:8080/api/governance/virtual-keys
```

Bifrost's governance API is unauthenticated by default and its Service is
deliberately ClusterIP-only. If you put it behind a token, add it to
`locol-ai-secrets` as `LOCOL_BIFROST_ADMIN_TOKEN`; the deployment already references
that key as `optional: true`.

## 8. DNS and TLS

1. Get the ingress load balancer address:
   ```bash
   kubectl get ingress -n locol-ai
   kubectl get svc -n ingress-nginx    # external IP/hostname of the LB
   ```
2. Create a DNS record for `<your-host>` pointing at that LB (an `A` record for an
   IP, or a `CNAME` for an AWS ELB hostname).
3. cert-manager sees the Ingress and issues the `locol-ai-tls` certificate
   automatically. Watch it with:
   ```bash
   kubectl describe certificate locol-ai-tls -n locol-ai
   ```

## 9. Verify

```bash
kubectl get pods -n locol-ai
kubectl logs -n locol-ai deploy/locol-ai -c locol-ai   # supervisord + all 3 procs
curl -I https://<your-host>/docs                        # BackEnd OpenAPI docs

# survey content mounted from the ConfigMap - expect all 8 files
kubectl -n locol-ai exec deploy/locol-ai -- ls /app/Web/question-sets

# JWT keys mounted from the secret - expect all FOUR, including both enc_* files.
# Only two means the secret predates the encrypted-token change: see section 4.
kubectl -n locol-ai exec deploy/locol-ai -- ls /keys
```

A pod stuck in `ContainerCreating` is almost always the missing `question-sets-config`
ConfigMap; `kubectl describe pod -n locol-ai` names it in the events.

A pod that starts cleanly but 500s on every authenticated request, with
`[ERROR] JWT key configuration` in the log, is the `/keys` check above coming back
with fewer than four files.

Open `https://<your-host>/` for the Web app and
`https://<your-host>/www/index.html` for the Content Editor.

To reach the sqlite-web admin UI safely (never expose it publicly):

```bash
kubectl port-forward -n locol-ai deploy/locol-ai 8080:8080
# then browse http://localhost:8080
```

## 10. Platform appendices

### <a name="eks-appendix"></a>Amazon EKS

- **Image:** push to ECR (section 3). Give the node group / pod an IAM role that
  allows `ecr:GetDownloadUrlForLayer` etc., or attach an ECR pull secret.
- **Storage:** install the **EBS CSI driver** add-on and use `gp3`. (The driver's
  service account typically uses IRSA — an IAM role for service accounts — for
  volume provisioning.)
- **Ingress:** ingress-nginx works as-is (it provisions a Network Load Balancer).
  Alternatively use the **AWS Load Balancer Controller** to get an ALB — if you do,
  set `ingressClassName: alb` and replace the nginx annotations with `alb.ingress.
  kubernetes.io/*` ones (scheme, target-type, certificate-arn or cert-manager).

### DigitalOcean Kubernetes (DOKS)

- **Image:** push to DOCR (section 3) and add the pull secret via
  `doctl registry kubernetes-manifest`.
- **Storage:** use `do-block-storage` for the RWO PVC. DO also offers `csi-s3`
  (Spaces-backed) if you ever need ReadWriteMany — e.g. to share the seed-config
  volume across multiple replicas — but the default single-replica setup does not.
- **Ingress:** install ingress-nginx (provisions a DO Load Balancer) and
  cert-manager; the manifests apply unchanged.

## 11. Production and security notes

- **`DEBUG` is `false`** in the portable Deployment — keep it that way in
  production (it otherwise logs verbose LLM/request detail).
- **The container runs as non-root** (UID 1000, `app`), with
  `allowPrivilegeEscalation: false` and all Linux capabilities dropped. The pod's
  `fsGroup: 1000` is **required, not decorative** — it is what makes the RWO volume at
  `/app/BackEnd/db` group-writable. Remove it and the BackEnd cannot create per-user
  databases; the pod starts and then fails on the first login. On OpenShift
  `restricted-v2`, drop `runAsUser`/`fsGroup` and let the platform assign a UID from
  the namespace range.
- **`readOnlyRootFilesystem` is not set.** `uv run` resolves the virtualenv at
  start-up, Streamlit writes under `$HOME` and supervisord writes a pidfile, so a
  read-only root would need `emptyDir` mounts over `/tmp` and `/home/app`. This is
  recorded as accepted residual risk in
  [security-management.md](./security-management.md#gaps-with-no-other-home).
- **Never expose sqlite-web** (port 8080) via the Service or Ingress; it's an
  unauthenticated database admin UI. Use `kubectl port-forward`.
- **Single replica + ReadWriteOnce:** the app is not currently horizontally
  scalable (each replica would need its own copy of the SQLite volume). The
  Deployment uses `strategy: Recreate` so upgrades don't deadlock on the volume.
- **Back up the `locol-ai-storage` PVC** — it holds all user data. Snapshot it
  via your cloud provider (EBS snapshots / DO volume snapshots).
- **Rotate keys** (`locol-ai-jwt-keys`, `locol-ai-db-key`) if they may have been
  exposed. Note the db-key caveat in section 4 before rotating it. `locol-ai-jwt-keys`
  holds four files and rotating it logs every user out, which is also the only way to
  revoke an issued token — there is no revocation list ([jwt.md](jwt.md) section 11).
- **All four JWT key halves sit in one secret mounted into one pod**, so the
  private/public split between `Web` and `BackEnd` is a code-level discipline, not a
  boundary this deployment enforces: anything with shell access in the pod can both
  mint a token and decrypt one. Splitting the two services into separate Deployments
  with a secret each is what would make it real.
- Set **resource requests/limits** appropriate to your load (the defaults in
  `03-deployment.yaml` are modest: 512Mi/100m requested, 1Gi/500m limit).
