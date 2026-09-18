#!/usr/bin/env bash
#
# Generate the two key pairs the session token needs.
#
# Usage: ./scripts/generate-jwt-keys.sh [--out-dir DIR] [--key-size N] [--force]
#
# The token is a nested JWT - an RS256-signed JWS wrapped in an ECDH-ES+A256KW
# JWE - so it takes one key pair per layer, written into --out-dir:
#
#   private_key.pem      RSA, PKCS#1, unencrypted. Web SIGNS with this.
#   public_key.pem       RSA, SubjectPublicKeyInfo. BackEnd VERIFIES with this.
#   enc_private_key.pem  EC P-256, SEC1. BackEnd DECRYPTS with this.
#   enc_public_key.pem   EC P-256, SubjectPublicKeyInfo. Web ENCRYPTS with this.
#
# Note the halves are held crosswise: each service has one private key and one
# public key, so neither can both mint and read a token on its own. See
# BackEnd/src/jwt_auth.py and Web/src/jwt_utils.py; both find this directory via
# the LOCOL_JWT_KEYS_LOCATION env var.
#
# Regenerating these pairs is cheap: it only invalidates existing sessions, so
# users simply log in again.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

OUT_DIR="$REPO_ROOT/keys"
KEY_SIZE=2048
FORCE=0

usage() {
    cat <<'EOF'
Generate a fresh RSA key pair for JWT signing/verification.

Usage: ./scripts/generate-jwt-keys.sh [--out-dir DIR] [--key-size N] [--force]

Options:
  --out-dir DIR   Directory to write the key pair into (default: <repo>/keys)
  --key-size N    RSA key size in bits (default: 2048)
  --force         Overwrite an existing key pair in --out-dir
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
        --key-size)
            [ $# -ge 2 ] || { echo "Error: --key-size requires a value" >&2; exit 1; }
            KEY_SIZE="$2"
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

case "$KEY_SIZE" in
    ''|*[!0-9]*) echo "Error: --key-size must be a number, got '$KEY_SIZE'" >&2; exit 1 ;;
esac
if [ "$KEY_SIZE" -lt 2048 ]; then
    echo "Error: --key-size must be at least 2048" >&2
    exit 1
fi

if ! command -v openssl > /dev/null 2>&1; then
    echo "Error: openssl not found on PATH. Install it (macOS: preinstalled or 'brew install openssl';" >&2
    echo "       Debian/Ubuntu: 'apt install openssl') and rerun." >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

PRIVATE_KEY_PATH="$OUT_DIR/private_key.pem"
PUBLIC_KEY_PATH="$OUT_DIR/public_key.pem"
ENC_PRIVATE_KEY_PATH="$OUT_DIR/enc_private_key.pem"
ENC_PUBLIC_KEY_PATH="$OUT_DIR/enc_public_key.pem"

if [ "$FORCE" -eq 0 ]; then
    for existing in "$PRIVATE_KEY_PATH" "$PUBLIC_KEY_PATH" "$ENC_PRIVATE_KEY_PATH" "$ENC_PUBLIC_KEY_PATH"; do
        if [ -e "$existing" ]; then
            echo "Refusing to overwrite existing key(s) in $OUT_DIR. Pass --force to replace them." >&2
            exit 1
        fi
    done
fi

# OpenSSL 3.x defaults genrsa to PKCS#8; -traditional restores the PKCS#1
# output OpenSSL 1.x (and the Python script this replaces) produced. The flag
# doesn't exist on 1.x, so probe for it rather than branching on version.
TRADITIONAL_FLAG=""
if openssl genrsa -traditional -out /dev/null 512 > /dev/null 2>&1; then
    TRADITIONAL_FLAG="-traditional"
fi

echo "Generating a ${KEY_SIZE}-bit RSA key pair..."

# umask so the private key is never briefly readable by others. Output goes
# through `tr -d '\r'` because Git Bash's OpenSSL build writes CRLF on Windows,
# which would make the PEMs differ from the ones the .ps1 script produces.
(
    umask 077
    # shellcheck disable=SC2086
    openssl genrsa $TRADITIONAL_FLAG "$KEY_SIZE" 2> /dev/null | tr -d '\r' > "$PRIVATE_KEY_PATH"
)
chmod 600 "$PRIVATE_KEY_PATH"

openssl rsa -in "$PRIVATE_KEY_PATH" -pubout 2> /dev/null | tr -d '\r' > "$PUBLIC_KEY_PATH"

echo "Generating a P-256 EC key pair..."

# `ecparam -genkey` emits a SEC1 "EC PRIVATE KEY" on both OpenSSL 1.x and 3.x,
# which is also what the .ps1 script's hand-rolled encoder produces. (`genpkey`
# would emit PKCS#8 instead, and the two scripts would disagree.) --key-size does
# not apply here: P-256 is fixed by the ECDH-ES+A256KW choice in the token format.
(
    umask 077
    openssl ecparam -name prime256v1 -genkey -noout 2> /dev/null | tr -d '\r' > "$ENC_PRIVATE_KEY_PATH"
)
chmod 600 "$ENC_PRIVATE_KEY_PATH"

openssl ec -in "$ENC_PRIVATE_KEY_PATH" -pubout 2> /dev/null | tr -d '\r' > "$ENC_PUBLIC_KEY_PATH"

echo "Wrote $PRIVATE_KEY_PATH      (RSA private - Web signs)"
echo "Wrote $PUBLIC_KEY_PATH       (RSA public  - BackEnd verifies)"
echo "Wrote $ENC_PRIVATE_KEY_PATH  (EC private  - BackEnd decrypts)"
echo "Wrote $ENC_PUBLIC_KEY_PATH   (EC public   - Web encrypts)"
