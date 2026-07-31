#!/usr/bin/env bash
# build_fileio_demo.sh
# Build pipeline for examples/fileio_demo.has:
#   HAS -> .s -> object files -> linked .exe

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD="$ROOT/build"
LIB="$ROOT/lib"
SRC="$ROOT/examples/fileio_demo.has"

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

echo "=== Build: fileio_demo ==="

echo "[1/3] Compile HAS -> assembly"
(cd "$ROOT" && "$PYTHON" -m hasc.cli "$SRC" -o "$BUILD/fileio_demo.s")

echo "[2/3] Assemble objects"
"$VASM" -Fhunk -devpac -I "$LIB" "$BUILD/fileio_demo.s" -o "$BUILD/fileio_demo.o"
"$VASM" -Fhunk -devpac -I "$LIB" "$LIB/fileio.s" -o "$BUILD/fileio.o"
"$VASM" -Fhunk -devpac -I "$LIB" "$LIB/takeover.s" -o "$BUILD/takeover.o"

echo "[3/3] Link executable"
"$VLINK" -bamigahunk \
    "$BUILD/fileio_demo.o" \
    "$BUILD/fileio.o" \
    "$BUILD/takeover.o" \
    -o "$BUILD/fileio_demo.exe"

echo "Done: $BUILD/fileio_demo.exe"
