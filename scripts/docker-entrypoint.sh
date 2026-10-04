#!/usr/bin/env bash
#
# Container entrypoint: report on the start-up artifacts and, when asked to, create the
# ones that are missing - then hand off to the command the image was given (supervisord,
# see the CMD in /Dockerfile).
#
# The image needs three things that cannot be baked into it, because every one of them
# is either a secret or user data:
#
#   keys/{private,public,enc_private,enc_public}_key.pem   the session-token key pairs
#   keys/db_encryption.key                                 Fernet key for LLM keys at rest
#   BackEnd/db/persistent_data.sqlite                      the shared accounts database
#
# CREATING THEM IS OPT-IN: set LOCOL_BOOTSTRAP=true. Left unset, this script only looks
# and reports, and creates nothing.
#
# That default is deliberately the cautious one, because the two deployments want
# opposite things:
#
#   - A single-host `docker compose up` (docs/deploy-compose.md) has nowhere else for
#     these to come from, so the compose file sets LOCOL_BOOTSTRAP=true and an empty
#     ./data becomes a working install with no setup step.
#   - A Kubernetes deployment (docs/deploy-k8s.md) provisions all of them outside the
#     pod - the keys as Secrets, the database on a PVC - and must NOT have artifacts
#     seeded underneath it. A key generated inside a pod would live on the container
#     filesystem, vanish on the next restart, and take every stored LLM API key with it
#     if it were the Fernet one. So an unset flag changes nothing there, whatever the
#     manifests say.
#
# When creation is on, it delegates to the same three generators the host-side installer
# uses, so there is one implementation of each artifact:
#
#   scripts/generate-jwt-keys.sh
#   scripts/generate-db-encryption-key.sh
#   scripts/create_user_database.py
#
# and takes the same contract as scripts/setup-local.sh: every step detects whether it is
# already done and skips it, and nothing is ever regenerated or overwritten. It NEVER
# passes --force. Regenerating keys/db_encryption.key makes every stored LLM API key
# permanently undecryptable, so a half-present set is reported as an error for a human to
# resolve rather than repaired by guessing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# The same two variables the application reads - BackEnd/src/jwt_auth.py::_keys_dir()
# and BackEnd/src/db_crypto.py::_load_key(). Resolving them here rather than hardcoding
# a path is what keeps this from looking somewhere the app does not: in Kubernetes they
# are /keys and /db-key (two separate Secrets), while the image's own ENV points both
# at /keys.
#
# The fallbacks match the app's own defaults, which are relative to BackEnd's working
# directory - so an image built without the ENV block still agrees with the services.
KEYS_DIR="${LOCOL_JWT_KEYS_LOCATION:-$APP_ROOT/keys}"
DB_KEY_DIR="${LOCOL_DB_ENCRYPTION_KEY_LOCATION:-$KEYS_DIR}"

# Fixed by MAIN_DB_PATH in BackEnd/src/db_manager.py, which is relative to the
# `directory=/app/BackEnd` supervisord runs the BackEnd from. The per-user databases
# that live alongside it are created on demand at registration, not here.
DB_PATH="$APP_ROOT/BackEnd/db/persistent_data.sqlite"
DB_KEY_PATH="$DB_KEY_DIR/db_encryption.key"

JWT_KEY_NAMES=(private_key.pem public_key.pem enc_private_key.pem enc_public_key.pem)

# Step name -> outcome, printed as a summary before exec so `docker compose logs` or
# `kubectl logs` shows at a glance whether a start touched anything. Parallel arrays
# rather than an associative one, to match setup-local.sh.
SUMMARY_NAMES=()
SUMMARY_VALUES=()

step()   { printf '\n==> %s\n' "$1"; }
note()   { printf '    %s\n' "$1"; }
warn()   { printf 'WARNING: %s\n' "$1" >&2; }
record() { SUMMARY_NAMES+=("$1"); SUMMARY_VALUES+=("$2"); }

# A key file counts as present only if it is non-empty and, for a PEM, actually starts
# with a PEM header. A truncated or placeholder file otherwise fails much later as an
# opaque parse error from jwcrypto rather than as missing setup. Same check as
# setup-local.sh::key_file_ok.
key_file_ok() {
    local path="$1" pem="${2:-}"
    [ -s "$path" ] || return 1
    if [ "$pem" = "pem" ]; then
        head -n 1 "$path" | grep -q '^-----BEGIN' || return 1
    fi
    return 0
}

# Every real SQLite file opens with this 16-byte magic string. A truncated or
# placeholder file otherwise fails later as "file is not a database".
db_file_ok() {
    [ -s "$DB_PATH" ] || return 1
    head -c 15 "$DB_PATH" | grep -q '^SQLite format 3' || return 1
    return 0
}

# Named so the fix for the most likely failure is printed, not inferred. Docker creates
# a missing bind-mount source directory as root, while this image runs as UID 1000 - so
# on Linux a first `docker compose up` against a ./data that the archive did not create
# dies here. The alternative is a bare "Permission denied" from openssl several lines
# deeper, with nothing naming the host directory it came from.
require_writable() {
    local dir="$1" what="$2"
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir" 2> /dev/null || true
    fi
    if [ ! -d "$dir" ] || [ ! -w "$dir" ]; then
        cat >&2 <<EOF
Error: cannot write $what to $dir

This container runs as UID 1000, and that directory is either missing or owned by
another user. If it is a bind mount (the docker-compose.yml ships ./data/keys and
./data/db), fix the ownership on the host and start again:

  sudo chown -R 1000:1000 ./data
EOF
        exit 1
    fi
}

# Invoked through bash rather than relying on the executable bit, which a checkout on a
# filesystem without permission bits may not preserve. Same reasoning as
# setup-local.sh::run_repo_script.
run_repo_script() {
    local name="$1"
    shift
    local path="$SCRIPT_DIR/$name"
    if [ ! -f "$path" ]; then
        echo "Error: missing $path - the image is incomplete." >&2
        exit 1
    fi
    bash "$path" "$@"
}

# --- Is creating artifacts switched on? --------------------------------------

BOOTSTRAP=0
case "${LOCOL_BOOTSTRAP:-}" in
    1|true|TRUE|True|yes|YES|on|ON) BOOTSTRAP=1 ;;
esac

# --- Take stock --------------------------------------------------------------
#
# Done for both modes before anything is written, so the report is the same whether or
# not this start is allowed to act on it.

PRESENT_KEYS=""
MISSING_KEYS=""
for key_name in "${JWT_KEY_NAMES[@]}"; do
    if key_file_ok "$KEYS_DIR/$key_name" pem; then
        PRESENT_KEYS="$PRESENT_KEYS  present: $KEYS_DIR/$key_name
"
    else
        MISSING_KEYS="$MISSING_KEYS  missing: $KEYS_DIR/$key_name
"
    fi
done

DB_KEY_PRESENT=0
key_file_ok "$DB_KEY_PATH" && DB_KEY_PRESENT=1

DB_PRESENT=0
db_file_ok && DB_PRESENT=1

echo "Locol Content AI: checking start-up artifacts"
note "JWT keys:       $KEYS_DIR"
note "DB encryption:  $DB_KEY_DIR"
note "Users database: $APP_ROOT/BackEnd/db"

# --- Report-only mode (the default) ------------------------------------------

if [ "$BOOTSTRAP" -eq 0 ]; then
    step "Creating artifacts is off (LOCOL_BOOTSTRAP is not set)"

    if [ -z "$MISSING_KEYS" ]; then
        note "Session-token key pairs: present"
    else
        note "Session-token key pairs: INCOMPLETE"
        printf '%s' "$MISSING_KEYS"
    fi
    [ "$DB_KEY_PRESENT" -eq 1 ] && note "DB encryption key:       present" \
                                || note "DB encryption key:       MISSING ($DB_KEY_PATH)"
    [ "$DB_PRESENT" -eq 1 ] && note "Users database:          present" \
                            || note "Users database:          missing ($DB_PATH)"

    # Warn, but start anyway. The pod/container coming up and failing at the point of
    # use - with BackEnd logging which path it could not read - is the behaviour
    # docs/deploy-k8s.md section 4 documents for a Secret that is missing or predates
    # the encrypted session token. Refusing to start instead would turn that into a
    # CrashLoopBackOff and defeat the `optional: true` backward compatibility the
    # manifests are careful to keep.
    if [ -n "$MISSING_KEYS" ] || [ "$DB_KEY_PRESENT" -eq 0 ]; then
        echo
        warn "Starting anyway, but authentication cannot work until the files above exist.
         Every authenticated request will return 500 'Server authentication key is not
         configured', and BackEnd will log the path it could not read.

         Supply them the way your deployment is meant to:
           Kubernetes - as the locol-ai-jwt-keys and locol-ai-db-key Secrets
                        (docs/deploy-k8s.md section 4). This is the correct place:
                        a key generated in the pod is lost on the next restart.
           single host - set LOCOL_BOOTSTRAP=true to have this container generate
                        them into its mounted volumes (docs/deploy-compose.md)."
    fi

    echo
    exec "$@"
fi

# --- Creation mode (LOCOL_BOOTSTRAP is on) -----------------------------------

step "Session-token key pairs (4 files in $KEYS_DIR)"

# Four files, two pairs: RSA for the signature, EC P-256 for the JWE wrapper the signed
# token is sealed in. It is all four or none - any partial set means some part of the
# token path has no usable key, and every login fails. See docs/jwt.md.
if [ -z "$MISSING_KEYS" ]; then
    note "Already present - skipping."
    record "JWT key pairs" "already present"
elif [ -n "$PRESENT_KEYS" ]; then
    # The generator refuses to write over the files that exist, and this script never
    # passes --force, so hand the decision back rather than guessing which half is the
    # good one. Only reachable with creation switched on, which means a single-host
    # install - where starting half-configured is worse than not starting.
    cat >&2 <<EOF
Error: found an incomplete set of session-token keys:
${PRESENT_KEYS}${MISSING_KEYS}
A mismatched or partial set fails on every login, and nothing here will overwrite an
existing key. Either restore the missing file, or delete the ones that are present and
restart the container to generate a fresh set of four. Regenerating only invalidates
existing sessions - users log in again - and affects nothing else.
EOF
    exit 1
else
    require_writable "$KEYS_DIR" "the session-token key pairs"
    run_repo_script "generate-jwt-keys.sh" --out-dir "$KEYS_DIR"
    record "JWT key pairs" "created"
fi

step "Database encryption key ($DB_KEY_PATH)"

if [ "$DB_KEY_PRESENT" -eq 1 ]; then
    note "Already present - skipping."
    record "DB encryption key" "already present"
else
    require_writable "$DB_KEY_DIR" "the database encryption key"
    run_repo_script "generate-db-encryption-key.sh" --out-dir "$DB_KEY_DIR"
    record "DB encryption key" "created"
    echo
    warn "This key is not disposable. It encrypts the stored LLM API key of every user,
         there is one key for all of them, and there is no backup other than the file
         just created. If you lose or replace it after real keys have been saved, those
         values are permanently unrecoverable - and silently so.

         Back it up out of band now, before storing any real data. Under the compose
         deployment it is on the host at ./data/keys/db_encryption.key."
fi

step "Shared users database ($DB_PATH)"

if [ "$DB_PRESENT" -eq 1 ]; then
    note "Already present - skipping."
    record "Users database" "already present"
elif [ -e "$DB_PATH" ]; then
    cat >&2 <<EOF
Error: $DB_PATH exists but is not a usable SQLite database.

Nothing here will overwrite it, because a file in that state is more likely to be a
damaged database than a disposable one. Move it aside and restart the container to get
a fresh accounts database - note that doing so orphans the per-user databases next to
it, which are named by the user ids the file you moved holds.
EOF
    exit 1
else
    require_writable "$(dirname "$DB_PATH")" "the shared users database"
    # Reuses the BackEnd's own init_users_table(), so the schema has a single source of
    # truth. --db-path is left at the script's default: it resolves the path from its own
    # location, which is $APP_ROOT in the image, and so already agrees with MAIN_DB_PATH.
    #
    # Run from BackEnd/ with an absolute script path, which is the same invocation form
    # supervisord uses for the service itself - the one shape of `uv run` this image is
    # known to resolve, since it finds the project by walking up from the working
    # directory to /app/BackEnd/pyproject.toml.
    (cd "$APP_ROOT/BackEnd" && uv run python "$SCRIPT_DIR/create_user_database.py")
    record "Users database" "created"
fi

# --- Hand off ----------------------------------------------------------------

echo
echo "Start-up artifacts ready."
i=0
while [ "$i" -lt "${#SUMMARY_NAMES[@]}" ]; do
    printf '  %-20s %s\n' "${SUMMARY_NAMES[$i]}" "${SUMMARY_VALUES[$i]}"
    i=$((i + 1))
done
echo

# exec, so the supervisord that CMD names replaces this shell and becomes PID 1 itself -
# otherwise it would run as a child and never see the SIGTERM docker sends on stop,
# turning every `docker compose down` into a 10-second timeout and a SIGKILL.
exec "$@"
