#!/usr/bin/env bash
#
# Run a Bearer SAST scan over first-party source and write the report to
# bearer.log at the repo root.
#
# Usage: ./scripts/run-bearer-scan.sh [--out FILE] [--severity LIST] [--fail]
#
# Scope comes from bearer.yml and suppressions from bearer.ignore, both
# committed at the repo root - see the comments in bearer.yml for why
# dependencies and build output are excluded.
#
# Bearer does not need to be installed locally: if it is not on PATH this
# falls back to the official container image, which is how the report is
# normally produced.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BEARER_IMAGE="bearer/bearer:latest"
OUT_FILE="$REPO_ROOT/bearer.log"
SEVERITY="critical,high,medium,low"
FAIL=0

usage() {
    cat <<'EOF'
Run a Bearer SAST scan over first-party source.

Usage: ./scripts/run-bearer-scan.sh [--out FILE] [--severity LIST] [--fail]

Options:
  --out FILE       Write the report here (default: <repo>/bearer.log, gitignored)
  --severity LIST  Comma-separated severities to report
                   (default: critical,high,medium,low)
  --fail           Exit non-zero if any finding is reported. Off by default so
                   an ordinary scan always produces a readable report.
  -h, --help       Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --out)
            [ $# -ge 2 ] || { echo "Error: --out requires a value" >&2; exit 1; }
            OUT_FILE="$2"
            shift 2
            ;;
        --severity)
            [ $# -ge 2 ] || { echo "Error: --severity requires a value" >&2; exit 1; }
            SEVERITY="$2"
            shift 2
            ;;
        --fail)
            FAIL=1
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

# Without --exit-code 0 Bearer returns non-zero whenever it reports a finding,
# which would trip set -e before the report is ever written.
EXIT_CODE_ARG="--exit-code=0"
if [ "$FAIL" -eq 1 ]; then
    EXIT_CODE_ARG=""
fi

if command -v bearer > /dev/null 2>&1; then
    echo "Scanning with local bearer ($(bearer version 2>/dev/null | head -1))..."
    # shellcheck disable=SC2086
    bearer scan "$REPO_ROOT" \
        --severity "$SEVERITY" \
        $EXIT_CODE_ARG \
        | tee "$OUT_FILE"
elif command -v docker > /dev/null 2>&1; then
    echo "bearer not on PATH; scanning with $BEARER_IMAGE..."
    # /tmp/scan matches the paths in previous reports, so findings stay
    # comparable across runs. Mounted read-only: a scan never writes to the tree.
    # shellcheck disable=SC2086
    docker run --rm \
        -v "$REPO_ROOT:/tmp/scan:ro" \
        "$BEARER_IMAGE" scan /tmp/scan \
        --severity "$SEVERITY" \
        $EXIT_CODE_ARG \
        | tee "$OUT_FILE"
else
    echo "Error: neither bearer nor docker found on PATH." >&2
    echo "       Install Bearer (https://docs.bearer.com/guides/install/) or Docker and rerun." >&2
    exit 1
fi

echo
echo "Report written to $OUT_FILE"
