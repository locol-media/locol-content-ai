# Cutting a release

A release produces two things:

1. **An immutable container image** in GitHub Container Registry that a cluster can pull.
2. **A Docker Compose package** attached to the release — `locol-content-ai-<version>.zip`
   and `.tar.gz` — for people who want to run the app on one host rather than deploy it
   ([deploy-compose.md](deploy-compose.md)).

Both come from
[`../.github/workflows/publish-container.yml`](../.github/workflows/publish-container.yml):
the image is built from the repo-root `Dockerfile` (the same image described in
[deploy-k8s.md § 1](deploy-k8s.md#1-architecture-recap)), and the package is assembled
from [`../deploy/compose/`](../deploy/compose).

Package: **`ghcr.io/locol-media/locol-content-ai`**

## What publishes what

| Trigger | Tags produced | Release assets |
|---|---|---|
| Push to `main` | `:edge`, `:main-<short-sha>` | — |
| Release published, `v1.2.3` | `:1.2.3`, `:1.2`, `:1`, `:latest` | `locol-content-ai-1.2.3.{zip,tar.gz}` |
| Release published, `v0.2.0` | `:0.2.0`, `:0.2`, `:latest` | `locol-content-ai-0.2.0.{zip,tar.gz}` |
| Release published, `v1.0.0-rc.1` | `:1.0.0-rc.1`, and nothing else | `locol-content-ai-1.0.0-rc.1.{zip,tar.gz}` |
| `workflow_dispatch` | whatever the ref it runs from would produce | — |

Three deliberate choices in that table:

- **No `:0` tag for 0.x releases.** A major-version tag that moves across breaking
  0.x releases is a trap, and this project is pre-1.0. The `{{major}}` rule is
  disabled for `v0.*` in the workflow.
- **Prereleases never get `:latest`.** Marking a release as a prerelease in the
  GitHub UI is enough; the workflow reads `release.prerelease`.
- **`:edge` and `:latest` are independent.** `:latest` only ever moves on a published
  non-prerelease release, so a merge to `main` cannot move what production pulls.

Only `:X.Y.Z` is immutable. Everything else moves.

Prereleases *do* get the compose package, unlike `:latest` — a release candidate is
exactly the thing someone should be able to download and try.

## The compose package

The `package` job stages [`deploy/compose/`](../deploy/compose) into
`locol-content-ai-<version>/`, adds `LICENSE`, `COPYRIGHT` and `THIRD-PARTY-NOTICES.md`
(the image bundles AGPL-3.0 Intro.js, so the notices travel with it), and uploads a zip
and a tarball to the release.

Two things worth knowing about it:

- **The packaged compose file is pinned** to `:<version>`, rewritten from the
  `${LOCOL_IMAGE_TAG:-latest}` the repo copy carries. The job `grep`s to confirm the
  rewrite landed and fails if it did not — an archive that silently ran whatever
  `:latest` later became would defeat the point of downloading a version.
- **It is a separate job** holding `contents: write`, which the build job deliberately
  does not. It `needs: publish`, so the package never points at an image that has not
  been pushed yet.

The job requires the `v` prefix and fails the release without it, because the version in
the asset name has to match the image tag `type=semver` derived.

A release cut before `deploy/compose/` existed has no package, and nothing backfills one.
`workflow_dispatch` will not produce one either — the job is gated on the release event,
which a manual run does not carry. To add assets to an existing release, re-run that
release's own workflow run (`gh run rerun <id>`), which rebuilds the image from the tag
and uploads the package with `--clobber`.

## Cutting one

1. Decide the version. Both `BackEnd/pyproject.toml` and `Web/pyproject.toml` carry a
   `version` field; bump them together if you want them to match the tag — nothing
   enforces it, and the image tag is what actually identifies a build.
2. Create the release. Either in the GitHub UI (Releases → Draft a new release), or:

   ```bash
   gh release create v0.2.0 --generate-notes
   ```

   Add `--prerelease` for a release candidate.
3. Watch the build:

   ```bash
   gh run watch
   ```

4. Confirm the tags landed:

   ```bash
   docker buildx imagetools inspect ghcr.io/locol-media/locol-content-ai:0.2.0
   ```

5. Deploy it by pinning the tag in `k8s/03-deployment.yaml` and following
   [deploy-k8s.md](deploy-k8s.md).

The release tag is what the workflow reads, so `v` is required (`v0.2.0`, not
`0.2.0`) — `type=semver` strips it when naming the image tags.

## Verifying provenance

Release builds (not `:edge`) get a signed SLSA provenance attestation pushed
alongside the image:

```bash
gh attestation verify \
  oci://ghcr.io/locol-media/locol-content-ai:0.2.0 \
  --repo locol-media/locol-content-ai
```

This proves the image was built by that workflow from this repo, which is worth
checking if an image shows up with a tag nobody remembers cutting.

## Rolling back

Version tags are immutable, so rollback is just re-pinning:

```bash
kubectl set image deployment/locol-ai \
  locol-ai=ghcr.io/locol-media/locol-content-ai:0.1.0 \
  --namespace locol-ai
```

Then make it durable by editing `image:` in `k8s/03-deployment.yaml` to match —
otherwise the next `kubectl apply` undoes it. Note the Deployment uses the
`Recreate` strategy with a single replica and a ReadWriteOnce volume, so a rollback
is a brief outage, not a rolling swap.

## First-time setup

Done once per repository, and not something the workflow can do for itself:

1. The workflow must exist on `main` in `locol-media/locol-content-ai`. The image
   name comes from `${{ github.repository }}`, because `GITHUB_TOKEN` can only write
   to packages owned by the repo the workflow runs in — so running it from a fork
   publishes to the fork's own package, not upstream's.
2. The first push creates the package, **private by default**. Set visibility under
   repo → Packages → `locol-content-ai` → Package settings. Public is the simpler
   choice and sits consistently with the GPLv3 / AGPL source-offer obligation noted
   in the root `README.md`; private means every cluster needs a pull secret
   ([deploy-k8s.md](deploy-k8s.md#image-pull-secret-private-registries)).
3. Check Package settings → *Manage Actions access* lists this repository with
   **Write**. GitHub adds it automatically when the package is first pushed by the
   repo's own workflow, but verify rather than assume.
4. Check Settings → Actions → General → *Workflow permissions* is not restricted in
   a way that overrides the job's `packages: write`.

## Bumping the pinned `uv`

The `Dockerfile` pins the `uv` builder image (`ghcr.io/astral-sh/uv:0.12.23`) so a
release tag rebuilds identically months later. When bumping it, run the BackEnd suite
afterwards — `uv sync --frozen` is the build step most sensitive to the resolver
version, and both `uv.lock` files are lock-format revision 2:

```bash
docker build -t locol-ai:check .
cd BackEnd && uv run pytest tests/ -v
```
