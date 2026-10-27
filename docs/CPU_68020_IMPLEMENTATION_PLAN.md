# CPU 68020 Implementation Plan

Status: living roadmap and capability reference for the opt-in 68020 target.
Phases 0–2, the current 68020 arithmetic substitutions, and Phase 6 are
implemented. Memory-indirect addressing and several optional ISA features remain
deferred; see the phase statuses below.

## Purpose

Provide a practical, low-risk roadmap for expanding 68020 support while preserving default 68000 behavior and compatibility.

## Current Baseline

- `--cpu` supports `68000` and `68020`, default is `68000`.
- Phases 0–2 are implemented: target guardrails, scaled/full-extension indexed
  addressing, and conservative constant-index `.w` selection. `.w` selection
  is limited to constant indexes in the signed 16-bit range on supported 68020
  access paths; bounded-loop range analysis is not implemented.
- Phase 4 instruction substitution is implemented for arithmetic: `*`, `/`,
  `%` on `int`/`long` lower to native `muls.l`/`divsl.l` under `--cpu 68020`
  (`TargetSpec.supports_32bit_muldiv`), lifting the 68000-only signed 16-bit
  operand restriction for those operators on that target.
- Phase 4 instruction substitution also covers signed byte-to-long sign
  extension: signed `byte` local variable and stack-parameter loads lower
  to a single `extb.l` under `--cpu 68020` (`TargetSpec.supports_extb_l`)
  instead of the 68000 `ext.w`+`ext.l` pair. This is a pure instruction-count
  optimization with no compile-time-restriction difference between targets.
- Phase 5.1 is implemented: when both operands of `*`, `/`, `%` are unsigned,
  lowering uses `mulu.l`/`divul.l` on `--cpu 68020` and `mulu.w`/`divu.w`
  (without `ext.l` sign normalization) on `--cpu 68000`, with an unsigned
  `0..65535` operand-range check. Mixed signed/unsigned operands keep the
  signed lowering.
- Phase 6 efficiency follow-ups are implemented: long-branch size selection
  (`supports_long_branches`), arbitrary-stride `mulu.l`, and long/ptr data
  alignment (`prefers_long_alignment`). See Phase 6 below.
- Memory-indirect modes are deferred.

## Non-Goals (for now)

- Broad "replace everything with 68020 instructions" passes.
- Rare or privileged/system-oriented instructions without clear language/runtime need (for example: `CALLM`, `RTM`, `MOVEC`, `CAS2`).
- Enabling the 68020 instruction/data caches via `MOVEC`/CACR: supervisor /
  AmigaOS-owned; belongs in startup `asm`, not the compiler.
- Loop-head I-cache `cnop` padding (see Phase 5.4 cut rationale).
- Blind shift+mask → bitfield peephole without a language bitfield surface
  (see Phase 5.3).
- `PACK`/`UNPK` BCD: a digit lookup table beats them for score display.
- 68881/68882 FPU: requires a coprocessor that plain 68020 A1200s lack;
  runtime Q16.16 (Phase 5.2) covers the same need without the dependency.
- Memory-indirect addressing remains disabled; the capability flag is false
  for both targets until a concrete use case and legality tests justify it.

## Guiding Constraints

- Keep 68000 output stable by default.
- Keep feature additions deterministic and testable.
- Prefer localized lowering changes over global peephole rewrites.
- Gate each phase with compile+assemble checks.

## Phase 0: Guardrails and Test Scaffolding (implemented)

The target model, paired CPU regression coverage, and shared indexed-address
lowering contract are in place.

Implementation references:

- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`
- `docs/COMPILER_DEVELOPERS_GUIDE.md`

Regression coverage:

- Paired-target checks in `tests/test_cpu_target.py` and
  `tests/test_codegen_68020_indexing.py` guard against accidental 68020
  indexed forms in 68000 output.

## Phase 1: Full-Extension Indexed Addressing (implemented)

68020 scaled indexes and legal full-extension displacements are supported;
68000 retains its unscaled fallback lowering.

Implementation references:

- `hasc/target.py`
- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`
- `hasc/codegen.py`

Regression coverage is in `tests/test_codegen_68020_indexing.py`, including
large displacements, struct fields, and expression evaluation order.

## Phase 2: `.w` Index Selection (implemented, constant-only)

The compiler selects `.w` only when a supported call site proves the original
index is a constant in the signed 16-bit range. All uncertain/dynamic indexes
remain `.l`; loop-bound or general value-range analysis is not present.

Implementation references:

- `hasc/validator.py`
- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`
- `hasc/codegen.py`

Regression coverage checks signed-16-bit boundaries and verifies that dynamic
indexes retain `.l`; see `tests/test_codegen_68020_indexing.py`.

## Phase 3: Memory-Indirect Addressing (deferred; not implemented)

`TargetSpec.supports_memory_indirect` remains false for both targets. No
memory-indirect form is emitted; retain the existing fallback unless a
measurable user need justifies a separate implementation and test plan.

Tasks:

1. Enable target capability for memory-indirect mode on 68020.
2. Implement legality-checked lowering for selected patterns first.
3. Preserve current fallback for non-eligible cases.

Primary files:

- `hasc/target.py`
- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`

Tests/examples to add:

1. Pointer-heavy addressing patterns that currently require extra add/load steps.
2. Negative tests for illegal forms.

Exit criteria:

- Demonstrable instruction-count reduction in selected patterns.
- Clean assembler acceptance with `-m68020`.

## Phase 4: Targeted 68020 Instruction Substitutions

Selected substitutions are implemented in codegen: 32-bit multiply/divide,
signed byte extension, and other features listed in the baseline above and
Phase 6 below. This is not a general "replace everything" pass.

Good candidates:

1. Carefully scoped arithmetic lowering improvements where semantics are clear.
2. Feature-specific substitutions tied to explicit language constructs.

Defer unless justified:

- Rare instructions with little practical payoff for current HAS workflows.

Primary files:

- `hasc/codegen.py`
- `hasc/peepholeopt.py`

Exit criteria:

- Each substitution has focused tests and measurable benefit.
- No broad regression risk from aggressive rewrites.

## Phase 5: Optional Follow-Ups

Potential follow-ups that would need their own design, implementation, and
tests. These are not current compiler capabilities.

### 5.1 Unsigned 32-bit `mulu.l` / `divul.l` (smallest gap, highest certainty)

Status: implemented. Explicitly unsigned local/parameter operands use
`mulu.w`/`divu.w` under 68000 and `mulu.l`/`divul.l` under 68020 when the
arithmetic operands qualify; mixed signed/unsigned operands retain signed
lowering. Non-negative integer literals are neutral, but at least one operand
must have an eligible unsigned type. See
[OPERATORS.md](OPERATORS.md#unsigned-multiplydividemodulo) and
`tests/test_codegen_68020_arithmetic.py` for the current contract.

### 5.2 Runtime fixed-point arithmetic

Status: deferred. HAS converts supported decimal literals to Q16.16 values at
compile time, but has no runtime `q16` type or target-specific fixed-point
operator lowering. Any future proposal must define overflow, precision,
runtime-type, and 68000 fallback semantics before choosing an instruction
sequence. Do not treat this section as an implemented CPU feature.

### 5.3 Bitfield instructions (`bfextu`/`bfexts`/`bfins`/`bfffo`/`bfset`/`bfclr`/`bftst`)

Status: **not implemented; requires a language surface** (not a silent peephole).

No bitfield syntax or bitfield-instruction lowering is implemented. A future
68020-only lowering needs an explicit language surface and tests; do not infer
support from ordinary bitwise expressions.

### 5.4 Instruction-cache-aware alignment

Status: **data-label alignment implemented; loop-head I-cache padding cut.**

Long/pointer data-label alignment for 68020 is implemented in Phase 6.3.
Compiler-generated loop-head instruction-cache padding and automatic cache
control-register setup are not implemented and remain out of scope.

### Phase 5 status

```
5.1 implemented
5.2 deferred (runtime fixed-point design needed)
5.3 not implemented (bitfield language surface needed)
5.4 data alignment implemented; loop I-cache padding cut
Phase 6 implemented
```

## Phase 6: Emitted-code efficiency (implemented)

Goal: ship the remaining high-ROI 68020 codegen wins that do not require new
language surface, while keeping `--cpu 68000` stable aside from intentional
CPU-neutral branch-size selection (prefer `.s` when the displacement fits).

### 6.1 Long branches (`supports_long_branches`) — done

68020 adds `BRA.L` / `Bcc.L`. A late peephole pass in `hasc/peepholeopt.py`
(`_select_branch_sizes`) estimates PC-relative distances after other peephole
passes and selects:

- `.s` when the conservative estimated displacement magnitude is at most 124
  bytes (both CPUs)
- `.w` when the estimate is at most 32766 bytes
- `.l` when |disp| exceeds the word range **and** `supports_long_branches`

Primary files: `hasc/target.py`, `hasc/peepholeopt.py`.

### 6.2 Arbitrary-stride multiplication

For non-`{1,2,4,8,16,32}` strides through `32767`, 68020 uses
`mulu.l #stride,Dn` so the index is not truncated to a word. The 68000
fallback uses `mulu.w`; larger strides use full-width shift/add lowering.

Primary file: `hasc/indexed_address.py`.

### 6.3 Long/ptr data alignment (`prefers_long_alignment`) — done

When the flag is set, data/BSS labels for `long`/`ptr` (and structs containing
a long field) emit `cnop 0,4` if the running section offset is not 4-byte
aligned. Word-only labels still use `even` on both CPUs. No loop-head I-cache
padding.

Primary files: `hasc/target.py`, `hasc/codegen.py`.

Tests: `tests/test_codegen_68020_efficiency.py`, plus updated indexing /
`test_cpu_target` coverage.

### Deferred work

- Runtime Q16.16 arithmetic and 64-bit multiply/divide are not implemented;
  compile-time decimal-literal conversion is not a runtime fixed-point type.
- Bitfield instructions need an explicit HAS bitfield representation before
  they can be lowered safely.
- Memory-indirect indexed addressing remains disabled by the target model.
- Loop-head I-cache padding and compiler-managed CACR setup are out of scope.

Keep future proposals tied to a concrete language/runtime need, and update
their target scope and tests before describing them as supported behavior.

## Validation Matrix (Run Per Phase)

1. Compile representative examples with `--cpu 68000` and `--cpu 68020`.
2. Assemble with matching CPU flags (`-m68000`, `-m68020`).
3. Run positive and negative example sets.
4. Spot-check generated assembly for intended mode-specific deltas only.
5. Preserve the invariant: default 68000 path must remain stable.

Example commands:

```bash
python3 -m hasc.cli examples/add.has --cpu 68000 -o /tmp/add-68000.s
python3 -m hasc.cli examples/add.has --cpu 68020 -o /tmp/add-68020.s
vasmm68k_mot -m68000 -Fhunkexe -o /tmp/add-68000.o /tmp/add-68000.s
vasmm68k_mot -m68020 -Fhunkexe -o /tmp/add-68020.o /tmp/add-68020.s
```

## Documentation Update Checklist Per Implementation PR

1. Update indexed-addressing behavior in
   `docs/COMPILER_DEVELOPERS_GUIDE.md#indexed-addressing-and-cpu-targets`.
2. Update user-facing target notes in `docs/DEVELOPERS_GUIDE.md`.
3. Add user-visible changes to `docs/CHANGELOG.md`.
4. Include one minimal before/after assembly example in PR notes.

## Definition of Done (Overall)

- 68020 support is materially improved for indexed addressing.
- 68000 default output and workflows remain stable.
- New behavior is documented, tested, and reproducible.
