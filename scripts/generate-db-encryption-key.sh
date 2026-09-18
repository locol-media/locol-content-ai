#!/usr/bin/env bash
#
# Generate a fresh Fernet key for encrypting APIkey values at rest.
#
# Usage: ./scripts/generate-db-encryption-key.sh [--out-dir DIR] [--force]
#
# Writes db_encryption.key into --out-dir. BackEnd's config_manager.py,
# load_llms.py, and llm.py all read this same key via the
# LOCOL_DB_ENCRYPTION_KEY_LOCATION env var (see BackEnd/src/db_crypto.py).
#
# WARNING: unlike the JWT keypair, this key protects data at rest, not just
# sessions. Once any APIkey values have been encrypted under a given key,
# regenerating the key with --force makes those values permanently
# undecryptable. db_crypto.py raises rather than guessing, and leaves the stored
# values alone, so the original key still recovers them - but nothing else will.
# Only use --force before any real data has been encrypted with the current key.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OUT_DIR="$REPO_ROOT/keys"
FORCE=0

usage() {
    cat <<'EOF'
Generate a fresh Fernet key for encrypting APIkey values at rest.

Usage: ./scripts/generate-db-encryption-key.sh [--out-dir DIR] [--force]

Options:
  --out-dir DIR   Directory to write the key into (default: <repo>/keys)
  --force         Overwrite an existing key in --out-dir (see the warning at
                  the top of this script - this destroys stored API keys)
  -h, --help      Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --out-dir)
            [ $# -ge 2 ] || { echo "Error: --out-dir requires a value" >&2; exit 1; }
            OUT_DIR="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument '$1'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if ! command -v openssl > /dev/null 2>&1; then
    echo "Error: openssl not found on PATH. Install it (macOS: preinstalled or 'brew install openssl';" >&2
    echo "       Debian/Ubuntu: 'apt install openssl') and rerun." >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

KEY_PATH="$OUT_DIR/db_encryption.key"

if [ "$FORCE" -eq 0 ] && [ -e "$KEY_PATH" ]; then
    echo "Refusing to overwrite existing key at $KEY_PATH. Pass --force to replace it." >&2
    exit 1
fi

# A Fernet key is 32 random bytes in URL-safe base64 (the '-_' alphabet).
# db_crypto.py strips surrounding whitespace, so the trailing newline is fine;
# the \r is dropped because Git Bash's OpenSSL build writes CRLF on Windows.
(
    umask 077
    openssl rand -base64 32 | tr -d '\r' | tr '+/' '-_' > "$KEY_PATH"
)
chmod 600 "$KEY_PATH"

echo "Wrote $KEY_PATH"
