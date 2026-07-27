#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="${HASC_PYTHON:-$ROOT/.venv/bin/python}"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="${HASC_PYTHON:-$ROOT/venv/bin/python}"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="${HASC_PYTHON:-python3}"
else
    PYTHON_BIN="${HASC_PYTHON:-python}"
fi

echo "Running HAS<->vbcc interop tests"
echo "  root: $ROOT"
echo "  python: $PYTHON_BIN"
echo "  vbcc target: ${VBCC_TARGET:-aos68k}"

cd "$ROOT"
"$PYTHON_BIN" -m pytest tests/test_vbcc_interop.py -v
