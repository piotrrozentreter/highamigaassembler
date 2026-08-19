# Motorola 68020 Compiler Target Plan

## Purpose

Add an opt-in Motorola 68020 code-generation target to HAS while preserving Motorola 68000
as the default and compatibility baseline.

The first implementation should focus on the 68020 scaled indexed addressing modes that
improve dynamic array, pointer, and struct-array access. It should not attempt to use every
68020 instruction or full effective-address form in the initial release.

## Compatibility Contract

- The default target remains Motorola 68000.
- Compiling without a CPU option must produce byte-for-byte identical assembly to explicitly
  selecting `68000`.
- The proposed CLI is `--cpu {68000,68020}`.
- Existing Python callers using `CodeGen(module)` must continue to select 68000 behavior.
- Selecting 68020 changes generated assembly, not HAS source syntax, data layout, ABI, calling
  convention, alignment, or pointer representation.
- 68020 output is not expected to execute on a 68000 or 68010.
- Inline `asm` remains the programmer's responsibility; the compiler cannot prove that inline
  assembly matches the selected CPU.
- A 68020 CPU target does not imply AGA, an FPU, or a particular Amiga chipset.

## Primary Optimization

The 68020 supports scaled index factors `1`, `2`, `4`, and `8` in indexed effective addresses.
This allows code such as:

```asm
; Existing 68000 lowering for a long array
lsl.l   #2,d1
move.l  (a0,d1.l),d0

; Proposed 68020 lowering
move.l  (a0,d1.l*4),d0
```

Use `.l` indexes initially. Changing to `.w` would introduce 16-bit truncation and sign
extension and is not semantics-preserving for all current programs.

Only scales supported directly by the CPU should use scaled indexing. Arbitrary element or
struct strides must retain explicit arithmetic.

## Current Implementation Surfaces

Array effective-address calculation is duplicated in several code-generation paths:

- Struct-array member reads in `hasc/codegen.py` near the `MemberAccess` expression handling.
- Local typed-pointer and global array reads in the `ArrayAccess` expression handling.
- Two-dimensional array reads in the same `ArrayAccess` handling.
- Address-of array elements in the unary `&` handling.
- Struct-array member stores in `_emit_stmt()`.
- Ordinary one- and two-dimensional array stores in `_emit_stmt()`.

Other affected surfaces:

- `hasc/cli.py`: CLI definition and `CodeGen` construction.
- `hasc/peepholeopt.py`: unconditional post-codegen optimization and regex-based operand analysis.
- `hasc/register_allocator.py`: documents intended register roles, although current codegen
  mostly uses hardcoded `d0`-`d3` and `a0` scratch registers.
- Build scripts and example Makefiles: many assume or explicitly pass `-m68000`.
- `scripts/test_runtime_musashi.sh`: currently does not propagate a compiler, assembler, or
  runner CPU target.
- `tools/musashi_runner/has_musashi_runner.c`: already accepts
  `--cpu 68000|68010|68EC020|68020`.

## Completed Prerequisite

Struct-array member stores previously calculated the destination in `a0`/`d1` before evaluating
the RHS. Calls or nested array expressions could clobber those registers before the final store.

The current branch contains the prerequisite fix:

- Struct-array member stores evaluate the RHS before forming the destination address.
- `tests/test_codegen_basic.py` contains
  `test_struct_array_member_store_evaluates_rhs_before_address`.

Verify that this test is present and passing before starting target work. On Linux, also add or
run a Musashi regression that proves the destination changes and the source array remains
unchanged after a nested RHS read and procedure call.

## Implementation Status

### Phases 0 and 1 complete

- Added focused tests proving that compiling without `--cpu` and compiling with
  `--cpu 68000` produce byte-for-byte identical assembly.
- Preserved `CodeGen(module)` as a 68000 API call and covered its equivalence to an
  explicit 68000 target.
- Added the closed `CpuTarget`/`TargetSpec` model with conservative capabilities:
  68000 has no 68020 address extensions, while 68020 records scaled-index support but
  keeps full extension and memory-indirect forms disabled.
- Added `--cpu {68000,68020}` to the CLI. Invalid values are rejected by argparse.
- Passed the selected target explicitly through `CodeGen` into the peephole optimizer.
  No emitter or optimizer rewrite is target-dependent yet, so both supported targets
  intentionally produce the current 68000 assembly.

The next implementation step is Phase 2: centralize indexed-address lowering and keep
the 68000 fallback byte-for-byte stable before enabling any 68020 output. That work and
the later assembler/Musashi validation should continue on Linux, where the 68000/68020
toolchain and runtime checks are available.

### Phase 2 Path 1 complete; Paths 2-6 ready for continuation on Linux

**Path 1 (Global 1D array reads) - COMPLETE**:
- Implemented `emit_1d_array_read()` in new `codegen_indexed_address.py` module.
- Converted codegen.py line ~842 to call centralized helper.
- Fixed dead-code branch (constants filtered before calling helper).
- Added assertion to enforce variable-index contract.
- Test passing: byte/word/long arrays produce identical baseline output, vasm validates both targets.
- Pattern established for remaining paths.

**Paths 2-6 Prepared**:
- `codegen_indexed_address.py` contains helper stubs:
  - `emit_typed_pointer_read()` — local/global typed-pointer indexing
  - `emit_array_address_of()` — address-of array elements with struct support
  - Paths 4-6 require new wrappers for store operations
- Phase 2 conditionals (scaled operands) remain disabled in `_lower_indexed_address()` with TODO markers.
- vasm validation framework complete and working on Windows.

**Next steps (on Linux with full toolchain)**:
1. **Path 2**: Convert local typed-pointer reads (~line 750-790). Complexity: local variable offset handling.
2. **Path 3**: Convert address-of array elements (~line 1350-1420). Complexity: struct array sizes, non-power-of-2 strides.
3. **Path 4**: Struct-array member stores (~line 2550-2650). New helper: `emit_struct_array_store()`. Complexity: RHS evaluation ordering.
4. **Path 5**: 1D array stores (~line 2640-2750). New helper: `emit_array_store()`. Complexity: destination calculation.
5. **Path 6**: 2D array operations (~line 900-1000). Extend `emit_array_store()` for row-major linearization.

Each path follows the same pattern: filter constants before calling helper, pass through centralized address lowering, emit Phase 2 baseline output identical to inline implementation.

**Phase 2 completion criteria**: All 6 paths route through `_lower_indexed_address()`, all tests pass, vasm validates both targets, example suite compiles without regressions.

## Proposed Target Model

Do not scatter string comparisons such as `if cpu == "68020"` throughout codegen. Introduce a
small closed target model, for example in `hasc/target.py`:

```python
from dataclasses import dataclass
from enum import Enum


class CpuTarget(str, Enum):
    M68000 = "68000"
    M68020 = "68020"


@dataclass(frozen=True)
class TargetSpec:
    cpu: CpuTarget
    supports_scaled_index: bool
    supports_full_index_extension: bool
```

Initial capabilities should be conservative:

| Target | Scaled index | Full extension | Memory indirect |
|---|---:|---:|---:|
| 68000 | No | No | No |
| 68020 phase 1 | Yes | No | No |

Keep full-extension and memory-indirect capabilities disabled until separately implemented and
validated. The model should allow later targets without turning CPU selection into several
unrelated booleans.

## Effective-Address Lowering Design

Centralize target-dependent address selection before enabling scaled output. A helper should own:

- Base register.
- Index register and index width.
- Element or struct stride.
- Optional field displacement.
- Temporary-register clobbers.
- Minimum CPU capability.
- Prelude instructions needed for the fallback.
- Rendered vasm Motorola-syntax effective address.

A minimal interface may return a prelude and operand:

```python
prelude, operand = self._lower_indexed_address(
    base_reg="a0",
    index_reg="d1",
    stride=4,
    displacement=0,
)
```

Expected results:

```python
# 68000
(["    lsl.l #2,d1"], "(a0,d1.l)")

# 68020
([], "(a0,d1.l*4)")
```

The exact API may follow existing code style, but all loads, stores, and address-of operations
must eventually consume the same legality rules.

Do not implement scaled indexing as a global peephole text replacement. Removing a shift changes
the index register value and condition-code side effects, requiring more context than the current
regex optimizer owns.

## Ordered Implementation Plan

### Phase 0: Freeze Baseline Behavior

1. Add tests proving no CPU option and `--cpu 68000` produce identical assembly.
2. Preserve `CodeGen(module)` as a 68000 API call.
3. Select representative golden or exact sequence tests for:
   - Byte, word, and long arrays.
   - Typed pointers.
   - Struct arrays.
   - Address-of array elements.
   - Two-dimensional arrays.
4. Explicitly assemble baseline output with `vasmm68k_mot -m68000`.

Gate: no target-dependent codegen work starts until the default-output contract is executable.

### Phase 1: Add Target Plumbing Without Output Changes

1. Add the target enum/specification.
2. Add `--cpu {68000,68020}` to `hasc/cli.py`, defaulting to `68000`.
3. Pass the target through `CodeGen` and into the peephole optimizer.
4. Keep all emitters producing current 68000-style output for both targets at this phase.
5. Test invalid CPU diagnostics and Python API defaults.

Gate: the complete existing example compilation set has the same pass/fail results as baseline.

### Phase 2: Centralize Indexed Address Lowering

1. Introduce the shared address-lowering helper.
2. Convert one path at a time while keeping generated 68000 output unchanged:
   - Primitive 1D read.
   - Primitive 1D store.
   - Typed pointer read.
   - Address-of.
   - Struct-array read and store.
   - Two-dimensional read and store.
3. After each path, run focused tests and compare 68000 output against baseline.
4. Document scratch-register and condition-code behavior in the helper contract.

Gate: all relevant paths use the helper or have an explicit documented reason not to.

### Phase 3: Apply Safe 68000 Indexed-Address Improvements

The 68000 already supports a signed 8-bit displacement with an unscaled index, for example:

```asm
move.w  6(a0,d1.l),d0
```

Where safe, replace separate field-offset additions with this legal 68000 form. This is not a
68020 feature and benefits both targets. Keep this change separately testable from scaled index
generation so baseline changes are intentional and reviewable.

Gate: displacement boundaries and resulting assembly are validated with `-m68000`.

### Phase 4: Enable Primitive 68020 Scaled Indexing

Implement the smallest useful 68020 feature set:

1. Byte arrays and byte pointers: scale 1, with no redundant shift.
2. Word arrays and word pointers: scale 2.
3. Long/int arrays and pointers: scale 4.
4. Cover both loads and stores.
5. Keep constant-index accesses as direct constant offsets.
6. Preserve `.l` index semantics.

Gate: every 68020 sample assembles with `-m68020`, and at least one scaled-index sample is
rejected by `-m68000` to prove that the test exercises a 68020 encoding.

### Phase 5: Address-Of and Struct Arrays

1. Emit scaled indexed `lea` or equivalent address formation for `&array[index]`.
2. Optimize struct strides `1`, `2`, `4`, and `8`.
3. Combine a legal field displacement with the scaled index.
4. Preserve explicit arithmetic for unsupported strides such as `3`, `6`, `10`, `12`, and `16`.
5. Cover struct member loads, stores, and address-of.
6. Include RHS calls and nested indexed expressions in store tests.

Gate: runtime tests prove source and destination arrays retain correct values for multiple indexes.

### Phase 6: Two-Dimensional Arrays

Keep the existing row-major calculation:

```text
linear_index = row * column_count + column
```

Initially fold only the final element-size multiplication into the 68020 effective address.
Do not change the existing row multiplication semantics in the same patch.

Gate: constant, mixed constant/dynamic, and fully dynamic indexes produce identical runtime
results on both targets.

### Phase 7: Harden Optimizer and Build Integration

1. Ensure peephole operand analysis handles scaled operands such as `(a0,d1.l*4)`.
2. Add tests for displacement-plus-scale forms and commas inside operands.
3. Ensure target-specific forms cannot be introduced in 68000 mode.
4. Propagate CPU selection to build scripts and example Makefiles where appropriate.
5. Use explicit vasm flags rather than assembler defaults:
   - `-m68000` for baseline output.
   - `-m68020` for 68020 output.

Gate: dual-target assembly succeeds across representative examples and default output contains no
scaled-index forms.

### Phase 8: Musashi Runtime Matrix

Extend `scripts/test_runtime_musashi.sh` with explicit target variables, for example:

```bash
HASC_CPU="${HASC_CPU:-68000}"
MUSASHI_CPU="${MUSASHI_CPU:-$HASC_CPU}"
```

Use them in all three stages:

```bash
python -m hasc.cli input.has --cpu "$HASC_CPU" -o output.s
vasmm68k_mot "-m$HASC_CPU" -Fbin -o output.bin output.s
has-musashi-runner output.bin --cpu "$MUSASHI_CPU"
```

Run equivalent semantic programs under both targets. Add a runtime program covering:

- Byte, word, and long array reads and writes.
- Typed pointer indexing.
- Struct strides 4 and 8.
- An unsupported struct stride fallback.
- Address-of array elements.
- Two-dimensional arrays.
- Indexes `0`, `1`, and the last valid element.
- A safely allocated case with an index above `32767` to catch accidental `.w` truncation.
- Nested RHS array/member access and a procedure call.
- PASS/FAIL reporting through the existing MMIO convention.

Gate: both CPU runs reach PASS, and running genuinely 68020-encoded output as 68000 does not
reach PASS.

### Phase 9: Documentation and Release

Update documentation only when behavior is implemented and validated:

- `README.md`: default target, opt-in usage, and compatibility warning.
- `docs/DEVELOPERS_GUIDE.md`: CLI and matching vasm options.
- `docs/INSTALL.md`: target-specific toolchain verification.
- `docs/ARRAY_ACCESS_IMPLEMENTATION.md`: side-by-side lowering and fallback rules.
- `docs/COMPILER_DEVELOPERS_GUIDE.md`: target propagation and address-lowering architecture.
- `docs/CHANGELOG.md`: user-visible opt-in feature and unchanged default.
- Example Makefiles or build documentation that hardcode `-m68000`.

Gate: documentation states exactly what is implemented and does not imply AGA, FPU, or full
68020 instruction-set optimization.

## Test Matrix

| Access form | 68000 expectation | 68020 expectation |
|---|---|---|
| Byte array/pointer | Unscaled index | Unscaled or explicit `*1` |
| Word array/pointer | Explicit `lsl.l #1` | Scaled `*2` |
| Long array/pointer | Explicit `lsl.l #2` | Scaled `*4` |
| Struct stride 8 | Explicit `lsl.l #3` | Scaled `*8` |
| Struct stride 6 | Existing multiply/fallback | Same legal fallback |
| Constant index | Constant displacement | Same constant displacement |
| 2D long array | Linearize, then shift | Linearize, then scaled `*4` |
| Struct field offset | Legal target displacement or fallback | Legal displacement plus scale |
| Address-of | Explicit scale and add | Scaled indexed `lea` or equivalent |

For each applicable row, test reads, stores, and address formation. Include complex index
expressions and RHS calls so register lifetime is exercised.

## Important Correctness Risks

### Target Leakage

Any scaled or full-extension operand in default output breaks 68000 compatibility. The default
target and explicit `68000` tests must remain mandatory.

### Register Lifetime

Codegen mostly hardcodes scratch registers rather than relying on `RegisterAllocator`. Address
formation must happen after RHS evaluation for stores, and nested index expressions must preserve
partial values correctly.

### Index Width and Signedness

Keep `.l` indexes. Do not replace existing operations with `.w` forms without range proof.
Current `mulu.w` paths already have low-word behavior; changing those paths can alter semantics
and must not be bundled with scaled indexing.

### Condition Codes

`lsl` and `mulu` affect condition codes; indexed effective-address calculation does not. Most
generated consumers establish their own flags, but address-of expressions and peephole test
removal require focused checks.

### Displacement Legality

The 68000 brief indexed displacement is signed 8-bit. Larger displacements must retain explicit
arithmetic until 68020 full-extension rendering is separately supported and assembler-tested.

### Optimizer Parsing

The peephole optimizer uses string and regex analysis. Scaled/full operands add syntax that can
break register-modification detection or unsafe store folding. Add regression tests before such
operands flow through optimizer passes.

### Hardware and ABI Assumptions

Do not change alignment, struct layout, stack slots, register convention, chip-memory placement,
or custom-register access. A 68EC020-based A1200 still has platform-specific bus and address-space
constraints that are independent of the compiler's instruction selection.

## Deferred Work

Keep these out of the initial implementation:

- Full-extension indexed addressing with larger base displacement.
- Memory-indirect pre-indexed and post-indexed forms.
- 68020 long multiply/divide substitutions.
- Bit-field instructions.
- `.w` index selection.
- ABI, alignment, or struct-layout changes.
- 68030/68040 cache-specific behavior.
- Automatic validation of inline assembly.

Each deferred feature should have its own motivation, benchmarks, instruction-level tests, and
assembler/runtime validation.

## Validation Commands

### Focused Python Tests

```bash
python -m pytest tests/test_codegen_basic.py -v
python -m pytest tests/test_peepholeopt.py -v
python -m pytest tests/test_codegen_68020_indexing.py -v
```

The last file is proposed and should be created for target-specific codegen tests.

### Explicit Assembly Checks

```bash
python -m hasc.cli input.has --cpu 68000 -o /tmp/test-68000.s
vasmm68k_mot -m68000 -Fbin -o /tmp/test-68000.bin /tmp/test-68000.s

python -m hasc.cli input.has --cpu 68020 -o /tmp/test-68020.s
vasmm68k_mot -m68020 -Fbin -o /tmp/test-68020.bin /tmp/test-68020.s
```

### Musashi Matrix

After harness propagation is implemented:

```bash
HASC_CPU=68000 MUSASHI_CPU=68000 ./scripts/test_runtime_musashi.sh
HASC_CPU=68020 MUSASHI_CPU=68020 ./scripts/test_runtime_musashi.sh
```

### Broader Regression

```bash
python -m pytest tests -v
./scripts/tests/test_examples_split.sh
```

Record pre-existing failures separately. Do not widen the 68020 task to unrelated failures.

## Definition of Done

- `--cpu 68000` and `--cpu 68020` are accepted; unknown values fail clearly.
- No option and explicit `68000` produce identical assembly.
- Existing `CodeGen(module)` callers remain 68000-compatible.
- Primitive dynamic arrays and typed pointers use legal scaled indexing under 68020.
- Struct strides 1, 2, 4, and 8 are optimized where legal.
- Unsupported strides and displacements use correct fallback code.
- Loads, stores, address-of, and two-dimensional arrays are covered.
- Target-specific output is assembled with explicit matching vasm CPU flags.
- Musashi semantic tests pass under both selected CPUs.
- At least one 68020 output is rejected by `-m68000` or fails to reach PASS on a 68000 runner,
  proving the target-specific path was exercised.
- Default 68000 examples retain their previous compilation behavior.
- Documentation and changelog accurately describe the implemented scope.

## Recommended First Session Scope

The first implementation session should complete only Phases 0 and 1:

1. Freeze default-output behavior with focused tests.
2. Add the target model and `--cpu` plumbing.
3. Preserve identical output for both targets temporarily.
4. Run focused tests and the existing example compilation sweep.

This establishes a reviewable target boundary before changing instruction selection.

Suggested opening prompt for the implementation session:

```text
Implement Phases 0 and 1 from docs/MOTOROLA_68020_TARGET_PLAN.md.

Add the conservative CPU target model and --cpu {68000,68020} plumbing, keeping 68000 as the
default and preserving current generated assembly for both targets in this phase. Add tests that
prove no option and explicit --cpu 68000 are identical and that CodeGen(module) remains a 68000
API. Pass the target explicitly into codegen and the peephole optimizer, but do not emit scaled
indexed addressing yet. Run focused pytest checks and the example compilation sweep. Keep edits
limited to this phase and report any pre-existing failures separately.
```