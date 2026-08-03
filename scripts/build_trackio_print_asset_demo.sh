#!/usr/bin/env bash
# build_trackio_print_asset_demo.sh
# Build pipeline for examples/trackio_print_asset_demo.has:
#   HAS -> .s -> object files -> linked .exe

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD="$ROOT/build"
LIB="$ROOT/lib"
SRC="$ROOT/examples/trackio_print_asset_demo.has"

VASM="${VASM:-vasmm68k_mot}"
if ! command -v "$VASM" &>/dev/null; then
    echo "ERROR: vasmm68k_mot not found. Set VASM=/path/to/vasmm68k_mot." >&2
    exit 1
fi

VLINK="${VLINK:-vlink}"
if ! command -v "$VLINK" &>/dev/null; then
    echo "ERROR: vlink not found. Set VLINK=/path/to/vlink." >&2
    exit 1
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="${HASC_PYTHON:-$ROOT/.venv/bin/python}"
elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
    PYTHON="${HASC_PYTHON:-$ROOT/.venv/Scripts/python.exe}"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
    PYTHON="${HASC_PYTHON:-$ROOT/venv/bin/python}"
else
    PYTHON="${HASC_PYTHON:-python}"
fi

mkdir -p "$BUILD"

echo "=== Build: trackio_print_asset_demo ==="

echo "[1/3] Compile HAS -> assembly"
(cd "$ROOT" && "$PYTHON" -m hasc.cli "$SRC" -o "$BUILD/trackio_print_asset_demo.s")

echo "[2/3] Assemble objects"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$BUILD/trackio_print_asset_demo.s" -o "$BUILD/trackio_print_asset_demo.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/trackio.s" -o "$BUILD/trackio.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/takeover.s" -o "$BUILD/takeover.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/graphics.s" -o "$BUILD/graphics.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/sprite.s" -o "$BUILD/sprite.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/font8x8.s" -o "$BUILD/font8x8.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/helpers.s" -o "$BUILD/helpers.o"
"$VASM" -Fhunk -kick1hunks -I "$LIB" "$LIB/keyboard.s" -o "$BUILD/keyboard.o"

echo "[3/3] Link executable"
"$VLINK" -bamigahunk -Bstatic \
    "$BUILD/trackio_print_asset_demo.o" \
    "$BUILD/trackio.o" \
    "$BUILD/takeover.o" \
    "$BUILD/graphics.o" \
    "$BUILD/sprite.o" \
    "$BUILD/font8x8.o" \
    "$BUILD/helpers.o" \
    "$BUILD/keyboard.o" \
    -o "$BUILD/trackio_print_asset_demo.exe"

echo "Done: $BUILD/trackio_print_asset_demo.exe"
