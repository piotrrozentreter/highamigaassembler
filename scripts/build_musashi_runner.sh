#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNNER_SRC="$ROOT/tools/musashi_runner/has_musashi_runner.c"
MUSASHI_SRC_DIR="${MUSASHI_SRC_DIR:-$ROOT/build/musashi-src}"
OUT_BIN="${MUSASHI_RUNNER_BIN:-$ROOT/build/has-musashi-runner}"
CC_BIN="${CC:-gcc}"

if [[ "${OSTYPE:-}" != linux* ]]; then
    echo "ERROR: build_musashi_runner.sh is Linux-only." >&2
    echo "Run this workflow from Linux (native or WSL)." >&2
    exit 2
fi

if [[ ! -f "$RUNNER_SRC" ]]; then
    echo "ERROR: runner source missing: $RUNNER_SRC" >&2
    exit 1
fi

if ! command -v "$CC_BIN" >/dev/null 2>&1; then
    echo "ERROR: C compiler not found: $CC_BIN" >&2
    exit 1
fi

"$ROOT/scripts/setup_musashi.sh"

if [[ ! -f "$MUSASHI_SRC_DIR/m68kops.c" || ! -f "$MUSASHI_SRC_DIR/m68kops.h" ]]; then
    echo "Generating Musashi opcode tables (m68kops.c/h)"
    "$CC_BIN" -O2 -Wall -Wextra -pedantic -o "$MUSASHI_SRC_DIR/m68kmake" "$MUSASHI_SRC_DIR/m68kmake.c"
    (
        cd "$MUSASHI_SRC_DIR"
        ./m68kmake
    )
fi

mkdir -p "$(dirname "$OUT_BIN")"

echo "Building HAS Musashi runner"
"$CC_BIN" -O2 -Wall -Wextra -pedantic \
    -I"$MUSASHI_SRC_DIR" \
    "$RUNNER_SRC" \
    "$MUSASHI_SRC_DIR/m68kcpu.c" \
    "$MUSASHI_SRC_DIR/m68kdasm.c" \
    "$MUSASHI_SRC_DIR/m68kops.c" \
    "$MUSASHI_SRC_DIR/softfloat/softfloat.c" \
    -lm \
    -o "$OUT_BIN"

echo "Built runner: $OUT_BIN"
