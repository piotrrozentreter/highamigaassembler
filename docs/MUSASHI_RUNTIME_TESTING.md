# Musashi Runtime Testing (Linux Only)

This document describes an optional runtime-test tier for HAS using the
Musashi Motorola 68000 CPU emulator core.

For day-to-day usage, see `docs/MUSASHI_USER_GUIDE.md`.
This file focuses on technical integration details.

## Scope

- Focus: selected runtime tests that require real m68k instruction execution.
- Non-goal: full AmigaOS or chipset emulation.
- Current target: Linux only (native Linux or WSL).

## Why This Tier Exists

Current test coverage in HAS already includes parser, validator, codegen,
peephole, and link-interop checks. Musashi adds execution-time validation for
selected behavior such as:

- branch outcomes
- arithmetic semantics
- call/return behavior
- generated instruction runtime effects

## Files Added

- `tools/musashi.lock` - pinned upstream source reference.
- `scripts/setup_musashi.sh` - clones and checks out pinned Musashi source.
- `scripts/build_musashi_runner.sh` - builds the local Musashi runner.
- `scripts/test_runtime_musashi.sh` - executes selected runtime `.has` tests.
- `tools/musashi_runner/has_musashi_runner.c` - minimal host + MMIO protocol.
- `tests/runtime_musashi_manifest.txt` - selected runtime suite manifest.
- `examples/runtime_musashi/*.has` - initial runtime smoke tests.
- `tests/test_runtime_musashi.py` - optional pytest wrapper (Linux-gated).

## MMIO PASS/FAIL Protocol

The runner treats writes to the following addresses as test signals:

- `0x00100004` -> PASS event
- `0x00100000` -> FAIL event
- `0x00100014` -> write byte to stdout (debug trace)

A runtime test should emit one pass/fail signal and then stop or spin.

## Linux Workflow

1. Prepare pinned source:

```bash
./scripts/setup_musashi.sh
```

2. Build runner:

```bash
./scripts/build_musashi_runner.sh
```

3. Run selected runtime tests:

```bash
./scripts/test_runtime_musashi.sh
```

4. Optional pytest wrapper:

```bash
python -m pytest tests/test_runtime_musashi.py -v
```

## Updating Musashi Pin

To move to a newer upstream commit:

```bash
./scripts/update_musashi_pin.sh <git-ref>
# example: ./scripts/update_musashi_pin.sh master
```

This resolves the ref to an exact commit and rewrites `tools/musashi.lock`.

Recommended update process:

1. Update lock to a new commit.
2. Rebuild runner.
3. Run runtime suite.
4. Run existing compiler/unit/interops tests.
5. Document behavior deltas in changelog if any.

## Windows Note

This runtime workflow is intentionally Linux-only right now. On Windows,
this repository keeps the integration scaffolding and scripts so the work can
continue on Linux later without re-designing the architecture.
