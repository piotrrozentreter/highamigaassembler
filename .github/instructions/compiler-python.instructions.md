---
description: "Use when editing compiler Python sources in hasc, including parser, validator, codegen, allocator, CLI orchestration, and semantic bug fixes."
applyTo:
  - "hasc/**/*.py"
---

# HAS Compiler Python Instructions

## Primary Goal

Maintain compiler correctness and stable generated assembly while keeping changes minimal and reviewable.

## Required Engineering Rules

- Preserve parser -> validator -> codegen pipeline behavior unless the task explicitly changes it.
- When a task explicitly requires changing pipeline behavior or public APIs, document the change rationale in a comment at the change site and call out the deviation explicitly in the review output.
- Keep validator two-pass semantics intact: symbol collection before semantic checks.
- Do not store transient validation state inside AST nodes.
- In code generation, pair every register allocation with release on every control-flow path.
- Keep operand size behavior type-aware and consistent with expected byte, word, and long semantics.
- HAS targets two CPUs via `--cpu`: `68000` (default) and `68020` (opt-in). `hasc/target.py` (`TargetSpec`/`CpuTarget`) is the single source of truth for target capability flags (`supports_scaled_index`, `supports_full_index_extension`, `supports_memory_indirect`) - branch on these flags, never on ad-hoc `cpu == "68020"` string checks. Any change to indexed addressing, operand sizing, or instruction selection must preserve `--cpu 68000` default output (unless the change intentionally targets it) and must be considered/tested against `--cpu 68020` as well - do not assume a fix verified on one target holds for the other.

## Change Discipline

- Prefer localized edits over broad refactors.
- Keep public APIs and existing naming patterns stable unless change is required.
- Add concise comments only where logic is non-obvious.
- Keep error messages actionable and tied to source line context.

## Verification Expectations

- Run a smoke compile after any change to parser, validator, codegen, or allocator logic. Skip only for changes limited to comments, error message text, or CLI help strings.
- For parser and validator changes, include one valid and one invalid-path check where feasible.
- For codegen changes, verify generated assembly compiles when assembler tooling is available.
- For changes touching indexed addressing, operand sizing, or instruction selection, verify (or at minimum note as residual risk) behavior under BOTH `--cpu 68000` and `--cpu 68020`, assembling with the matching `vasmm68k_mot -m68000`/`-m68020` flag when the toolchain is available.

## Review Output Expectations

- Report behavior impact first, then implementation notes.
- Call out regression risk areas explicitly: register lifecycle, stack frame offsets, size suffixes, and control flow emission.
