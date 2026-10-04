# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set environment variables.
# UV_CACHE_DIR points into /tmp rather than under $HOME on purpose: the runtime
# user may not be `app` (OpenShift assigns an arbitrary UID whose home is not
# writable), and /tmp is 1777 for everyone. The directory is deliberately NOT
# created here - see the --no-cache note on the uv sync steps below.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_CACHE_DIR=/tmp/uv-cache

# Install system dependencies.
# openssl is here for scripts/docker-entrypoint.sh: the two key generators it delegates
# to shell out to the openssl CLI, which the python:*-slim base is not guaranteed to
# carry (libssl is not the command-line tool). Without it a first start against an
# empty volume fails at key generation instead of creating the keys.
RUN apt-get update && apt-get install -y \
    supervisor \
    openssl \
    sqlite3 nano \
    && rm -rf /var/lib/apt/lists/*

# Install uv. Pinned, not :latest - a release tag has to rebuild to the same image
# months later, and `uv sync --frozen` below is the step most sensitive to the
# resolver version. Both lockfiles are lock-format revision 2, written by an older
# uv; --frozen reads them as-is without rewriting, so a newer resolver is fine, but
# re-run the BackEnd suite when bumping this. Same reasoning as the sqlite-web pin
# further down - leaving a dependency unpinned is what let the bad release in there.
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy and install Web app dependencies.
# --no-cache is load-bearing, not an optimisation. These syncs run as root, while
# the container ends up running as `app` (or an arbitrary UID on OpenShift) and
# still shells out to `uv run` for both supervised programs. Without it, uv
# populates UV_CACHE_DIR (/tmp/uv-cache) as root:root 0755, and the first `uv run`
# at start-up dies with "Failed to initialize cache at /tmp/uv-cache ... Permission
# denied". Leaving the directory absent instead lets the runtime user create it
# themselves - /tmp is 1777, so this works for any UID. It also keeps the build
# cache out of the image layers. Nothing is lost: the cache is not reused across
# builds anyway (no BuildKit cache mount), and a cache hit on the layer skips the
# RUN entirely.
COPY Web/pyproject.toml Web/uv.lock ./Web/
WORKDIR /app/Web
RUN uv sync --frozen --no-dev --no-cache

# Copy and install BackEnd app dependencies
WORKDIR /app
COPY BackEnd/pyproject.toml BackEnd/uv.lock ./BackEnd/
WORKDIR /app/BackEnd
RUN uv sync --frozen --no-dev --no-cache

# Install sqlite-web using pip in a separate directory.
# Pinned deliberately: 0.8.0 ships a broken sqlite_web/__main__.py - it dropped a
# Python 2/3 version check and kept the Python 2 branch, so `from sqlite_web import
# main` resolves to the package (whose __init__.py is empty) and `python -m
# sqlite_web` dies with ImportError. 0.7.2 is the last release where that works.
# Check upstream before bumping. Everything else here is lockfile-pinned; leaving
# this unpinned is what let the bad release in.
WORKDIR /app
RUN mkdir -p sqlite-web && \
    python3 -m pip install --target /app/sqlite-web sqlite-web==0.7.2

# Copy application code
WORKDIR /app
COPY Web/ ./Web/
COPY BackEnd/ ./BackEnd/
COPY scripts/ ./scripts/
RUN rm -rf ./BackEnd/db

# Create supervisor configuration
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create non-root user for security. The UID is pinned rather than left to
# useradd's default so the deployment manifests can assert runAsUser: 1000 and
# fsGroup: 1000 against a known value - the same pair bifrost/k8s/02-deployment.yaml
# already uses. fsGroup is what makes the PVC mounted over /app/BackEnd/db writable
# by this user, so these two files move together: changing the UID here without
# changing the manifests leaves the app unable to create per-user databases.
# HOME is set explicitly so uv and Streamlit have a writable home under any
# invocation, not only ones that resolve it from /etc/passwd.
#
# /keys and /app/BackEnd/db are created here, empty and owned by app, because both are
# mount points the container must be able to write into. The line above deletes
# ./BackEnd/db after the copy, so without this the db bind mount would land on a path
# that does not exist in the image; and the entrypoint generates the key files into
# /keys on a first start, which it can only do if that directory is app's.
RUN useradd --create-home --uid 1000 --shell /bin/bash app && \
    mkdir -p /keys /app/BackEnd/db && \
    chown -R app:app /app /keys && \
    chown -R app:app /var/log/supervisor
ENV HOME=/home/app

# Ports the supervised processes listen on. These defaults are what make the
# %(ENV_...)s references in supervisord.conf resolve - supervisord refuses to start if
# any of them is unset, so they belong here rather than only in the k8s ConfigMap.
# Override at run time (docker -e, or the ConfigMap) to move a service off its default;
# LOCOL_USER_DB_PORT is read by BackEnd/start_user_db.sh, which is run by hand.
ENV LOCOL_BACKEND_PORT=8000 \
    LOCOL_WEB_PORT=8501 \
    LOCOL_SQLITE_WEB_PORT=8080 \
    LOCOL_USER_DB_PORT=8081

# Where the two services look for the session-token key pairs and the DB encryption key.
# Set here so the container has one canonical, mountable keys directory: without these,
# both resolve to a path relative to each service's working directory (/app/keys), which
# is inside the image rather than on a volume. docker-compose.yml bind-mounts ./data/keys
# over /keys, and scripts/docker-entrypoint.sh generates into whatever these name.
#
# Kubernetes overrides both from k8s/01-configmap.yaml (/keys and /db-key, two separate
# Secrets), so nothing about that deployment changes - these are only the defaults for
# `docker run` and compose.
ENV LOCOL_JWT_KEYS_LOCATION=/keys \
    LOCOL_DB_ENCRYPTION_KEY_LOCATION=/keys

# Expose ports. Metadata only, resolved at build time - a runtime override of the
# variables above changes what the processes bind, not what is declared here.
EXPOSE ${LOCOL_WEB_PORT} ${LOCOL_BACKEND_PORT} ${LOCOL_SQLITE_WEB_PORT}

# Drop to the unprivileged user. This must stay the last instruction before CMD:
# it follows every COPY and the chown above, so build artifacts remain owned by
# app. Anything added after this line is written as app and cannot use apt-get or
# write outside /app, /home/app and /tmp.
USER app

# Report on the start-up artifacts (key pairs, DB encryption key, users database) and,
# with LOCOL_BOOTSTRAP=true, create the missing ones - then exec the CMD below. Creating
# them is opt-in, not the default: a deployment that provisions them from outside, as
# k8s/ does with Secrets and a PVC, must not have artifacts seeded underneath it. The
# compose file in deploy/compose/ sets the flag, because a single host has nowhere else
# for them to come from.
#
# Invoked through /bin/bash rather than relying on the script's executable bit, which a
# checkout on a filesystem without permission bits - a Windows one - may not preserve.
ENTRYPOINT ["/bin/bash", "/app/scripts/docker-entrypoint.sh"]

# Start supervisor to manage both processes
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]