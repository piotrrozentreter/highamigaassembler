#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_FILE="$ROOT/tools/musashi.lock"
TMP_DIR="$(mktemp -d)"
LOCK_HELPER="$ROOT/scripts/musashi_lock.sh"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ $# -ne 1 ]]; then
    echo "Usage: ./scripts/update_musashi_pin.sh <git-ref>" >&2
    echo "Example: ./scripts/update_musashi_pin.sh master" >&2
    exit 2
fi

NEW_REF="$1"

if [[ "${OSTYPE:-}" != linux* ]]; then
    echo "ERROR: update_musashi_pin.sh is Linux-only." >&2
    echo "Run this workflow from Linux (native or WSL)." >&2
    exit 2
fi

if [[ ! -f "$LOCK_FILE" ]]; then
    echo "ERROR: lock file not found: $LOCK_FILE" >&2
    exit 1
fi

if [[ ! -f "$LOCK_HELPER" ]]; then
    echo "ERROR: lock helper missing: $LOCK_HELPER" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "$LOCK_HELPER"
musashi_lock_load "$LOCK_FILE"

if [[ -z "${MUSASHI_REPO:-}" ]]; then
    echo "ERROR: MUSASHI_REPO missing in $LOCK_FILE" >&2
    exit 1
fi

echo "Resolving ref '$NEW_REF' from $MUSASHI_REPO"
git -C "$TMP_DIR" init >/dev/null
git -C "$TMP_DIR" remote add origin "$MUSASHI_REPO"
git -C "$TMP_DIR" fetch --depth 1 origin "$NEW_REF" >/dev/null
NEW_COMMIT="$(git -C "$TMP_DIR" rev-parse FETCH_HEAD)"

TODAY="$(date +%F)"

cat > "$LOCK_FILE" <<EOF
# Musashi source pin for HAS runtime emulation tests
# Update using: ./scripts/update_musashi_pin.sh <git-ref>
MUSASHI_REPO=$MUSASHI_REPO
MUSASHI_REF=$NEW_COMMIT
MUSASHI_PINNED_ON=$TODAY
MUSASHI_NOTES=Pin updated from ref:$NEW_REF to exact commit for reproducible Linux builds.
EOF

echo "Updated $LOCK_FILE"
echo "Pinned commit: $NEW_COMMIT"
