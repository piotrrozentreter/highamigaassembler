#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_FILE="$ROOT/tools/musashi.lock"
MUSASHI_SRC_DIR="${MUSASHI_SRC_DIR:-$ROOT/build/musashi-src}"
LOCK_HELPER="$ROOT/scripts/musashi_lock.sh"

if [[ "${OSTYPE:-}" != linux* ]]; then
    echo "ERROR: setup_musashi.sh is Linux-only." >&2
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

if [[ ! "$MUSASHI_REF" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    echo "ERROR: MUSASHI_REF must be a git commit hash (7-40 hex chars): $MUSASHI_REF" >&2
    exit 1
fi

mkdir -p "$(dirname "$MUSASHI_SRC_DIR")"

if [[ ! -d "$MUSASHI_SRC_DIR/.git" ]]; then
    echo "Cloning Musashi into $MUSASHI_SRC_DIR"
    git clone "$MUSASHI_REPO" "$MUSASHI_SRC_DIR"
fi

echo "Fetching Musashi updates"
git -C "$MUSASHI_SRC_DIR" fetch --tags --prune origin

echo "Checking out pinned ref: $MUSASHI_REF"
git -C "$MUSASHI_SRC_DIR" checkout --detach "$MUSASHI_REF"

echo "Musashi source prepared at: $MUSASHI_SRC_DIR"
git -C "$MUSASHI_SRC_DIR" rev-parse --short HEAD
