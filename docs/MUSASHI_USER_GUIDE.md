# Musashi Runtime User Guide (Linux Only)

This guide answers a practical question:

Can I test HAS compiler-generated code on a virtual CPU?

Yes. On Linux (or WSL), HAS provides an optional Musashi-based runtime test
tier that compiles your `.has` program, assembles it, and executes it on a
virtual Motorola 68000 CPU.

Use this when you want execution-level confidence in generated code behavior
(branches, arithmetic, call/return flow), not just parse/codegen success.

## Linux-only status

This workflow is intentionally Linux-only right now.

- Supported: native Linux and WSL
- Not supported: Windows shells (PowerShell/CMD) for this runtime flow

## Quickstart

Run these commands from the repository root:

```bash
./scripts/setup_musashi.sh
./scripts/build_musashi_runner.sh
./scripts/test_runtime_musashi.sh
```

Optional pytest entrypoints:

```bash
python3 -m pytest tests/test_runtime_musashi.py -v
python3 -m pytest -m "runtime and musashi" -v
```

## Prerequisites

- Linux or WSL terminal
- `git`
- `python3`
- `gcc`
- `vasmm68k_mot` in `PATH`
- Python dependencies installed:

```bash
python3 -m pip install -r requirements.txt
```

Quick tool check:

```bash
command -v git
command -v python3
command -v gcc
command -v vasmm68k_mot
```

## Expected output and success signals

After setup:

- Musashi sources are prepared in `build/musashi-src`
- Pinned commit is read from `tools/musashi.lock`

After build:

- Runner binary exists at `build/has-musashi-runner`

After runtime test script:

- Tests listed in `tests/runtime_musashi_manifest.txt` are compiled and executed
- Summary should end with `fail=0`

For pytest runs:

- Runtime Musashi tests should report `PASSED`

## Troubleshooting

### Linux-only message from script

Cause:
- Running from a non-Linux shell.

Fix:
- Use a Linux or WSL terminal.

### Runner build fails

Cause:
- Missing C toolchain (`gcc`) or build dependencies.

Fix:
- Install/verify `gcc`, then rerun:

```bash
./scripts/build_musashi_runner.sh
```

### Runtime script exits with status 77

Cause:
- Missing Linux prerequisite (commonly assembler/toolchain).

Fix:
- Install missing tool(s), verify `vasmm68k_mot` is in `PATH`, rerun runtime test.

### Runtime test never reports PASS/FAIL

Cause:
- Test did not emit required MMIO signal.

Fix:
- Ensure test writes PASS or FAIL using the MMIO protocol described below.

## Add a new runtime test (MMIO PASS/FAIL protocol)

The Musashi runner treats MMIO writes as test signals:

- `0x00100004` -> PASS event
- `0x00100000` -> FAIL event
- `0x00100014` -> write one debug byte to stdout (optional)

### 1. Create a new test program

Add a `.has` file under `examples/runtime_musashi/`.

Minimal shape:

```has
code main:
    ; Optional test logic here
    asm "move.l #1,$00100004";  ; PASS
    asm "stop #$2700";
```

Use FAIL instead when asserting a failure path:

```has
asm "move.l #1,$00100000";  ; FAIL
```

### 2. Register it in the runtime manifest

Add the new file path to `tests/runtime_musashi_manifest.txt`.

### 3. Run runtime tests

```bash
./scripts/test_runtime_musashi.sh
```

### 4. Optional pytest verification

```bash
python3 -m pytest tests/test_runtime_musashi.py -v
```

Reference examples:

- `examples/runtime_musashi/smoke_mmio_pass.has`
- `examples/runtime_musashi/proc_math_branch_pass.has`

## Related documents

- Technical overview: `docs/MUSASHI_RUNTIME_TESTING.md`