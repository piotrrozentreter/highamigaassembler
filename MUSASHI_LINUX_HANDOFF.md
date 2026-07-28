# Musashi Linux Handoff Checklist

This checklist resumes the musashiop branch work on a Linux machine (native Linux or WSL).

## 1) Confirm branch and environment

```bash
git branch --show-current
uname -a
```

Expected:
- Branch is `musashiop`
- OS reports Linux

## 2) Install/verify required tools

```bash
command -v git
command -v python3
command -v gcc
command -v vasmm68k_mot
```

If `vasmm68k_mot` is missing, install vasm and ensure it is on PATH.

## 3) Verify Python dependencies

```bash
python3 -m pip install -r requirements.txt
```

Optional venv flow:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 4) Prepare pinned Musashi source

```bash
./scripts/setup_musashi.sh
```

Expected:
- Musashi cloned/fetched into `build/musashi-src`
- Checked out detached at pinned commit from `tools/musashi.lock`

## 5) Build local Musashi runner

```bash
./scripts/build_musashi_runner.sh
```

Expected binary:
- `build/has-musashi-runner`

## 6) Run selected runtime tests

```bash
./scripts/test_runtime_musashi.sh
```

Expected:
- Runtime examples from `tests/runtime_musashi_manifest.txt` compile/assemble/run
- Summary ends with `fail=0`

## 7) Optional pytest entrypoint

```bash
python -m pytest tests/test_runtime_musashi.py -v
python -m pytest -m "runtime and musashi" -v
```

## 8) Full regression confidence (recommended)

```bash
python -m pytest -q
./scripts/test_examples_split.sh
```

Run vbcc interop only if vbcc toolchain is installed:

```bash
./scripts/test_vbcc_interop.sh
```

## 9) Update Musashi pin when needed

```bash
./scripts/update_musashi_pin.sh <git-ref>
# example:
./scripts/update_musashi_pin.sh master
```

Then re-run:
1. `./scripts/build_musashi_runner.sh`
2. `./scripts/test_runtime_musashi.sh`
3. `python -m pytest -q`

## 10) Runtime test authoring contract

For tests executed by the runner:
- PASS signal: write long to `0x00100004`
- FAIL signal: write long to `0x00100000`
- Optional stdout byte: write to `0x00100014`

Reference examples:
- `examples/runtime_musashi/smoke_mmio_pass.has`
- `examples/runtime_musashi/proc_math_branch_pass.has`

## Common troubleshooting

1. Script says Linux-only
- You are on Windows shell. Run from Linux/WSL terminal.

2. Runner build fails at m68kops generation
- Ensure `gcc` is installed and runnable.

3. Runtime script exits 77
- Missing Linux prerequisite (usually assembler/toolchain). Install and retry.

4. No PASS/FAIL signal before cycle budget
- Test did not emit MMIO pass/fail write. Add explicit signal in HAS test.

## Files added for this integration

- `tools/musashi.lock`
- `scripts/musashi_lock.sh`
- `scripts/setup_musashi.sh`
- `scripts/build_musashi_runner.sh`
- `scripts/test_runtime_musashi.sh`
- `scripts/update_musashi_pin.sh`
- `tools/musashi_runner/has_musashi_runner.c`
- `tests/runtime_musashi_manifest.txt`
- `tests/test_runtime_musashi.py`
- `docs/MUSASHI_RUNTIME_TESTING.md`
