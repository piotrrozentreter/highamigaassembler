#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="${MUSASHI_RUNTIME_MANIFEST:-$ROOT/tests/runtime_musashi_manifest.txt}"
RUNNER_BIN="${MUSASHI_RUNNER_BIN:-$ROOT/build/has-musashi-runner}"
BUILD_DIR="${MUSASHI_RUNTIME_BUILD_DIR:-$ROOT/build/runtime_musashi}"
CYCLE_BUDGET="${MUSASHI_CYCLE_BUDGET:-4000000}"
HASC_CPU="${HASC_CPU:-68000}"
MUSASHI_CPU="${MUSASHI_CPU:-$HASC_CPU}"

if [[ "${OSTYPE:-}" != linux* ]]; then
    echo "SKIP: runtime Musashi tests are Linux-only" >&2
    exit 77
fi

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: runtime manifest not found: $MANIFEST" >&2
    exit 1
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="${HASC_PYTHON:-$ROOT/.venv/bin/python}"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="${HASC_PYTHON:-$ROOT/venv/bin/python}"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="${HASC_PYTHON:-python3}"
else
    PYTHON_BIN="${HASC_PYTHON:-python}"
fi

VASM_BIN="${VASM:-vasmm68k_mot}"
if ! command -v "$VASM_BIN" >/dev/null 2>&1; then
    echo "SKIP: assembler not found (expected vasmm68k_mot or VASM override)" >&2
    exit 77
fi

"$ROOT/scripts/build_musashi_runner.sh"

if [[ ! -x "$RUNNER_BIN" ]]; then
    echo "ERROR: runner binary missing after build: $RUNNER_BIN" >&2
    exit 1
fi

mkdir -p "$BUILD_DIR"

total=0
ok=0
fail=0

while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw%%#*}"
    line="${line%$'\r'}"
    line="${line#${line%%[![:space:]]*}}"
    line="${line%${line##*[![:space:]]}}"
    [[ -z "$line" ]] && continue

    test_rel="${line%%|*}"
    expected="${line#*|}"
    if [[ "$expected" == "$line" ]]; then
        expected="pass"
    fi

    if [[ "$expected" != "pass" && "$expected" != "fail" ]]; then
        echo "ERROR: invalid expected status '$expected' in manifest line: $line" >&2
        exit 1
    fi

    src="$ROOT/$test_rel"
    if [[ ! -f "$src" ]]; then
        echo "FAIL missing source: $test_rel"
        fail=$((fail + 1))
        total=$((total + 1))
        continue
    fi

    base="$(basename "${src%.has}")"
    asm="$BUILD_DIR/$base.s"
    bin="$BUILD_DIR/$base.bin"

    total=$((total + 1))

    echo "[runtime] compile $test_rel"
    (cd "$ROOT" && "$PYTHON_BIN" -m hasc.cli "$test_rel" --cpu "$HASC_CPU" -o "$asm") >/dev/null

    echo "[runtime] assemble $base -> flat bin"
    "$VASM_BIN" "-m$HASC_CPU" -Fbin -o "$bin" "$asm" >/dev/null

    echo "[runtime] execute $base"
    if "$RUNNER_BIN" "$bin" --cpu "$MUSASHI_CPU" --cycles "$CYCLE_BUDGET" >/dev/null; then
        rc=0
    else
        rc=$?
    fi

    if [[ "$expected" == "pass" ]]; then
        if [[ $rc -eq 0 ]]; then
            echo "PASS $test_rel"
            ok=$((ok + 1))
        else
            echo "FAIL $test_rel (runner exit=$rc)"
            fail=$((fail + 1))
        fi
    else
        if [[ $rc -ne 0 ]]; then
            echo "PASS(expected-fail) $test_rel"
            ok=$((ok + 1))
        else
            echo "FAIL expected-fail but passed: $test_rel"
            fail=$((fail + 1))
        fi
    fi
done < "$MANIFEST"

echo "Runtime summary: total=$total ok=$ok fail=$fail"

if [[ $fail -ne 0 ]]; then
    exit 1
fi

exit 0
