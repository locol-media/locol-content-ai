#!/usr/bin/env bash
#
# One-command local install: keys, users database, dependencies, optional LLM key.
#
# Usage: ./scripts/setup-local.sh [options]
#
# Runs every one-time setup step docs/deploy-local.md used to list by hand:
#
#   1. checks uv (and openssl) are installed
#   2. generates the JWT signing keypair      (scripts/generate-jwt-keys.sh)
#   3. generates the DB encryption key        (scripts/generate-db-encryption-key.sh)
#   4. creates the shared users database      (scripts/create_user_database.py)
#   5. syncs BackEnd and Web dependencies     (uv sync)
#   6. optionally writes an LLM provider key into BackEnd/config/default/llms/llm.yaml
#
# Step 6 defaults to leaving that file alone, and recommends setting your key in
# the app instead (Config Manager). llm.yaml is tracked by git, so a key written
# there can be committed into your own repo by accident; a key set in the app is
# encrypted at rest, per user, and never touches a tracked file.
#
# Every step detects whether it is already done and skips it, so the script is
# safe to re-run on a working install. It NEVER passes --force to the key
# generators: regenerating keys/db_encryption.key makes every stored LLM API key
# permanently undecryptable, silently. To deliberately replace a key, run its
# generator yourself with --force.
#
# Setup only - this does not start anything.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKEND_DIR="$REPO_ROOT/BackEnd"
WEB_DIR="$REPO_ROOT/Web"
KEYS_DIR="$REPO_ROOT/keys"
LLM_YAML="$BACKEND_DIR/config/default/llms/llm.yaml"

# The APIkey value shipped in the committed llm.yaml. Anything equal to this (or
# empty) means "no provider key configured yet".
LLM_PLACEHOLDER="LOCOL MEDIA AUTOMATIC INSERTION"

API_KEY=""
API_STYLE=""
MODEL=""
# Answer to the step 6 "write into the tracked llm.yaml?" prompt. Declared here so
# `set -u` still has a value if `read` never runs (or hits EOF).
WRITE_ANSWER=""
SKIP_LLM=0
SKIP_SYNC=0
NON_INTERACTIVE=0

# Step name -> outcome, printed as a summary at the end so a re-run makes it
# obvious nothing was touched. Two parallel arrays: bash 3.2 (macOS) has no
# associative arrays and no ordered iteration over them.
SUMMARY_NAMES=()
SUMMARY_VALUES=()

usage() {
    cat <<'EOF'
One-command local install for Locol Content AI.

Usage: ./scripts/setup-local.sh [options]

Options:
  --api-key KEY       LLM provider API key to write into llm.yaml. Passing this
                      is itself the opt-in: it writes without asking. Remember
                      llm.yaml is tracked by git.
  --api-style STYLE   Provider style for --api-key: openai, gemini, anthropic,
                      ollama, ... (default: openai)
  --model MODEL       Optional model id, e.g. google-gla:gemini-2.0-flash
  --skip-llm          Leave llm.yaml alone without asking. Already the default;
                      this just suppresses the question.
  --skip-sync         Skip 'uv sync' for both projects
  --non-interactive   Never prompt; without --api-key this behaves like --skip-llm,
                      which is also what step 6 does by default
  -h, --help          Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --api-key)
            [ $# -ge 2 ] || { echo "Error: --api-key requires a value" >&2; exit 1; }
            API_KEY="$2"; shift 2 ;;
        --api-style)
            [ $# -ge 2 ] || { echo "Error: --api-style requires a value" >&2; exit 1; }
            API_STYLE="$2"; shift 2 ;;
        --model)
            [ $# -ge 2 ] || { echo "Error: --model requires a value" >&2; exit 1; }
            MODEL="$2"; shift 2 ;;
        --skip-llm) SKIP_LLM=1; shift ;;
        --skip-sync) SKIP_SYNC=1; shift ;;
        --non-interactive) NON_INTERACTIVE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *)
            echo "Error: unknown argument '$1'" >&2
            usage >&2
            exit 1 ;;
    esac
done

step()    { printf '\n==> %s\n' "$1"; }
note()    { printf '    %s\n' "$1"; }
warn()    { printf 'WARNING: %s\n' "$1" >&2; }
record()  { SUMMARY_NAMES+=("$1"); SUMMARY_VALUES+=("$2"); }

# A key file counts as present only if it is non-empty and, for a PEM, actually
# starts with a PEM header. A truncated or placeholder file otherwise fails much
# later as an opaque parse error from cryptography rather than as missing setup.
key_file_ok() {
    local path="$1" pem="${2:-}"
    [ -s "$path" ] || return 1
    if [ "$pem" = "pem" ]; then
        head -n 1 "$path" | grep -q '^-----BEGIN' || return 1
    fi
    return 0
}

run_repo_script() {
    local name="$1"
    local path="$SCRIPT_DIR/$name"
    if [ ! -f "$path" ]; then
        echo "Error: missing $path - the repo checkout is incomplete." >&2
        exit 1
    fi
    # Invoke through bash rather than relying on the executable bit, which a
    # checkout on a filesystem without permission bits may not preserve.
    bash "$path"
}

# Sync can fail on a file another process is holding open - a genuinely transient
# sharing violation. Anything else repeats identically on every attempt, so read
# the error rather than waiting out the retries.
sync_uv_project() {
    local dir="$1" attempt
    for attempt in 1 2 3; do
        if (cd "$dir" && uv sync); then
            return 0
        fi
        warn "uv sync failed in $dir (attempt $attempt/3) - retrying in 3s in case a file was momentarily locked. If the error above repeats unchanged, it is not a lock; read it."
        sleep 3
    done
    return 1
}

# Reads a top-level scalar field out of the (flat) llm.yaml without needing a YAML
# parser - the whole point of this script is to run before any Python environment
# exists.
get_llm_field() {
    local field="$1"
    sed -n "s/^[[:space:]]*${field}[[:space:]]*:[[:space:]]*//p" "$LLM_YAML" |
        head -n 1 |
        sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

# Replaces a field's value in place, appending the line if it isn't there.
# Line-level rather than re-serialising the file: llm.yaml may carry APIurl or
# extra documents, all of which load_llms.py honours and a rewrite would drop.
#
# awk, not sed, so a key containing sed metacharacters (&, /, \) can't corrupt the
# file - and the value arrives through the environment rather than -v, because awk
# expands backslash escapes in a -v assignment. The output is single-quoted YAML,
# which has no escape sequences at all beyond '' for a literal quote (\047 is that
# quote, spelled in octal so it survives the surrounding shell quoting).
set_llm_field() {
    local field="$1" value="$2" tmp
    tmp="$(mktemp)"
    LOCOL_FIELD="$field" LOCOL_VALUE="$value" awk '
        BEGIN {
            field = ENVIRON["LOCOL_FIELD"]
            value = ENVIRON["LOCOL_VALUE"]
            gsub(/\047/, "\047\047", value)
            quoted = field ": \047" value "\047"
            done = 0
        }
        {
            if (!done && $0 ~ "^[ \t]*" field "[ \t]*:") {
                print quoted
                done = 1
            } else {
                print
            }
        }
        END { if (!done) print quoted }
    ' "$LLM_YAML" > "$tmp"
    cat "$tmp" > "$LLM_YAML"
    rm -f "$tmp"
}

echo "Locol Content AI local setup"
echo "Repo root: $REPO_ROOT"

# --- 1. Pre-flight -----------------------------------------------------------

step "Checking prerequisites"

# A VIRTUAL_ENV inherited from the parent shell does not match whichever project
# uv is syncing, so uv warns and ignores it on every call. Clear it so each `uv`
# command just uses its project's .venv.
unset VIRTUAL_ENV || true

if ! command -v uv > /dev/null 2>&1; then
    cat >&2 <<'EOF'
Error: uv is not on PATH. Both services use it as their package manager.

Install it, then re-run this script:
  https://docs.astral.sh/uv/getting-started/installation/

  curl -LsSf https://astral.sh/uv/install.sh | sh

You do not need to install Python separately - uv provisions its own interpreter
for the Python 3.12+ both projects require.
EOF
    exit 1
fi
note "uv found: $(command -v uv)"

if ! command -v openssl > /dev/null 2>&1; then
    cat >&2 <<'EOF'
Error: openssl is not on PATH. The key generators use it.
  macOS: preinstalled, or 'brew install openssl'
  Debian/Ubuntu: 'apt install openssl'
EOF
    exit 1
fi
note "openssl found: $(command -v openssl)"

# --- 2. JWT key pairs --------------------------------------------------------

step "JWT key pairs (keys/{private,public,enc_private,enc_public}_key.pem)"

# Four files, two pairs: RSA for the signature, EC P-256 for the JWE wrapper the
# signed token is sealed in. See scripts/generate-jwt-keys.sh for which service
# holds which half. It is all four or none - any partial set means some part of
# the token path has no usable key.
PRESENT_KEYS=""
MISSING_KEYS=""
for key_name in private_key.pem public_key.pem enc_private_key.pem enc_public_key.pem; do
    if key_file_ok "$KEYS_DIR/$key_name" pem; then
        PRESENT_KEYS="$PRESENT_KEYS  present: $KEYS_DIR/$key_name
"
    else
        MISSING_KEYS="$MISSING_KEYS  missing: $KEYS_DIR/$key_name
"
    fi
done

if [ -z "$MISSING_KEYS" ]; then
    note "Already present - skipping."
    record "JWT key pairs" "already present"
elif [ -n "$PRESENT_KEYS" ]; then
    # An incomplete set is worse than none: the generator refuses to write over the
    # files that exist, and a mismatched pair fails on every login. This script never
    # passes --force, so hand the decision back rather than guessing.
    cat >&2 <<EOF
Error: found an incomplete set of JWT keys:
${PRESENT_KEYS}${MISSING_KEYS}
A mismatched or partial set fails on every login, and this script will not
overwrite existing keys. Regenerate all four deliberately:
  ./scripts/generate-jwt-keys.sh --force

That only invalidates existing sessions - users just log in again. Nothing else
in the install is affected.
EOF
    exit 1
else
    run_repo_script "generate-jwt-keys.sh"
    record "JWT key pairs" "created"
fi

# --- 3. Database encryption key ----------------------------------------------

step "Database encryption key (keys/db_encryption.key)"

DB_KEY="$KEYS_DIR/db_encryption.key"
if key_file_ok "$DB_KEY"; then
    note "Already present - skipping."
    record "DB encryption key" "already present"
else
    run_repo_script "generate-db-encryption-key.sh"
    record "DB encryption key" "created"
    echo
    warn "This key is not disposable. It encrypts the stored LLM API keys of every user,
         there is one key for all of them, and there is no backup other than
         $DB_KEY. If you lose or replace it after real keys have been saved, those
         values are permanently unrecoverable - and silently so. Back the file up
         out of band before storing any real data."
fi

# --- 4. Shared users database ------------------------------------------------

step "Shared users database (BackEnd/db/persistent_data.sqlite)"

DB_PATH="$BACKEND_DIR/db/persistent_data.sqlite"
DB_USABLE=0
if [ -s "$DB_PATH" ]; then
    # A truncated or placeholder file otherwise fails later as "file is not a
    # database". Every real SQLite file opens with this 16-byte magic string.
    if head -c 15 "$DB_PATH" | grep -q '^SQLite format 3'; then
        DB_USABLE=1
    fi
fi

if [ "$DB_USABLE" -eq 1 ]; then
    note "Already present - skipping."
    record "Users database" "already present"
elif [ -e "$DB_PATH" ]; then
    echo "Error: $DB_PATH exists but is not a usable SQLite database. Move it aside and re-run" >&2
    echo "       this script, or run 'uv run --project BackEnd python scripts/create_user_database.py --force'" >&2
    echo "       if you are sure it is disposable." >&2
    exit 1
else
    (cd "$REPO_ROOT" && uv run --project BackEnd python scripts/create_user_database.py)
    note "Created $DB_PATH"
    record "Users database" "created"
fi

# --- 5. Dependencies ---------------------------------------------------------

step "Python dependencies (uv sync)"

if [ "$SKIP_SYNC" -eq 1 ]; then
    note "--skip-sync given - skipping."
    record "Dependencies" "skipped (--skip-sync)"
else
    note "Syncing BackEnd..."
    if ! sync_uv_project "$BACKEND_DIR"; then
        echo "Error: uv sync kept failing in $BACKEND_DIR - read the error above, it is not a transient lock." >&2
        exit 1
    fi
    note "Syncing Web..."
    if ! sync_uv_project "$WEB_DIR"; then
        echo "Error: uv sync kept failing in $WEB_DIR - read the error above, it is not a transient lock." >&2
        exit 1
    fi
    note "Both projects synced."
    record "Dependencies" "synced"
fi

# --- 6. LLM provider key -----------------------------------------------------

step "LLM provider key (BackEnd/config/default/llms/llm.yaml)"

if [ ! -f "$LLM_YAML" ]; then
    warn "$LLM_YAML not found - skipping. Restore it from git to configure a provider."
    record "LLM provider key" "skipped (llm.yaml missing)"
elif [ "$SKIP_LLM" -eq 1 ]; then
    note "--skip-llm given - leaving llm.yaml alone. Set your key in the app."
    record "LLM provider key" "set it in the app (--skip-llm)"
else
    CURRENT_KEY="$(get_llm_field APIkey)"
    if [ -n "$CURRENT_KEY" ] && [ "$CURRENT_KEY" != "$LLM_PLACEHOLDER" ] && [ -z "$API_KEY" ]; then
        note "A provider key is already configured - skipping."
        record "LLM provider key" "already present"
    else
        if [ -z "$API_KEY" ] && [ "$NON_INTERACTIVE" -eq 0 ]; then
            # Recommend the in-app route and state the risk BEFORE offering the
            # choice. Writing here seeds the same shared key into every future
            # user's database; a key set in Config Manager is encrypted at rest,
            # belongs to one user, and never touches a tracked file.
            note "Recommended: leave this file alone and set your key in the app."
            echo
            note "  1. Start both services, then open http://localhost:8501"
            note "  2. Register an account"
            note "  3. Sidebar 'Settings and Tools' -> 'Config Manager'"
            note "  4. Tab 'LLMs' -> expand 'Locol AI Default' -> set 'API Key' -> 'Update'"
            echo
            warn "llm.yaml is TRACKED BY GIT (unlike keys/, which is ignored). A key written
         here can be committed into your own repo, and it is seeded into every
         user's database rather than just yours."
            echo
            printf '    Write a provider key into llm.yaml anyway? [y/N]: '
            read -r WRITE_ANSWER
            case "$WRITE_ANSWER" in
                y|Y|yes|YES)
                    printf '    API key (blank to skip): '
                    read -r API_KEY
                    if [ -n "$API_KEY" ]; then
                        if [ -z "$API_STYLE" ]; then
                            printf '    API style [openai, gemini, anthropic, ollama] (default: openai): '
                            read -r API_STYLE
                        fi
                        if [ -z "$MODEL" ]; then
                            printf '    Model (blank for the provider default): '
                            read -r MODEL
                        fi
                    fi
                    ;;
                *)
                    note "Leaving llm.yaml alone."
                    API_KEY=""
                    ;;
            esac
        elif [ -z "$API_KEY" ]; then
            note "--non-interactive given and no --api-key - leaving llm.yaml alone."
        fi

        if [ -n "$API_KEY" ]; then
            [ -n "$API_STYLE" ] || API_STYLE="openai"
            set_llm_field APIkey "$API_KEY"
            set_llm_field APIstyle "$API_STYLE"
            if [ -n "$MODEL" ]; then
                set_llm_field model "$MODEL"
            fi
            note "Wrote APIstyle '$API_STYLE' and your key to $LLM_YAML"
            warn "Do not commit your key:
         'git diff -- BackEnd/config/default/llms/llm.yaml' will show it."
            record "LLM provider key" "written to llm.yaml ($API_STYLE)"
        else
            note "llm.yaml still holds the placeholder. Set your key in the app:"
            note "  'Config Manager' -> 'LLMs' -> 'Locol AI Default' -> 'API Key'"
            record "LLM provider key" "set it in the app (recommended)"
        fi
    fi
fi

# --- Summary -----------------------------------------------------------------

echo
echo "Setup complete."
echo
i=0
while [ "$i" -lt "${#SUMMARY_NAMES[@]}" ]; do
    printf '  %-20s %s\n' "${SUMMARY_NAMES[$i]}" "${SUMMARY_VALUES[$i]}"
    i=$((i + 1))
done
cat <<'EOF'

Next: start both services, one per terminal, from the repo root

  cd BackEnd && uv run python src/main.py
  cd Web && uv run streamlit run src/main.py --server.port=8501

(On Windows, ./run-web-debug.ps1 does both in one command.)

Then open http://localhost:8501 and register an account.
Set your LLM provider key there: 'Settings and Tools' -> 'Config Manager'
-> 'LLMs' -> 'Locol AI Default' -> 'API Key' -> 'Update'.
See docs/deploy-local.md for ports, configuration and troubleshooting.
EOF
