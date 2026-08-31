# CPU 68020 Implementation Plan

Status: planning document for incremental 68020 support in HAS

## Purpose

Provide a practical, low-risk roadmap for expanding 68020 support while preserving default 68000 behavior and compatibility.

## Current Baseline

- `--cpu` supports `68000` and `68020`, default is `68000`.
- 68020 support currently covers scaled indexed addressing, full-extension
  indexed addressing (Phase 1), and constant-index `.w` selection (Phase 2).
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
- Memory-indirect modes are deferred.

## Non-Goals (for now)

- Broad "replace everything with 68020 instructions" passes.
- Rare or privileged/system-oriented instructions without clear language/runtime need (for example: `CALLM`, `RTM`, `MOVEC`, `CAS2`).
- `PACK`/`UNPK` BCD: a digit lookup table beats them for score display.
- 68881/68882 FPU: requires a coprocessor that plain 68020 A1200s lack;
  runtime Q16.16 (Phase 5.2) covers the same need without the dependency.
- Memory-indirect addressing beyond Phase 3's scope: the mode costs multiple
  bus cycles on real silicon, and HAS's arrow operator already lowers cleanly.
  If Phase 3 cannot demonstrate a win, remove `supports_memory_indirect`
  rather than leaving a permanently unused flag in `hasc/target.py`.

## Guiding Constraints

- Keep 68000 output stable by default.
- Keep feature additions deterministic and testable.
- Prefer localized lowering changes over global peephole rewrites.
- Gate each phase with compile+assemble checks.

## Phase 0: Guardrails and Test Scaffolding

Goal: lock in safety before adding new 68020 lowering behavior.

Tasks:

1. Add regression checks that ensure 68000 path stays unchanged.
2. Add paired example checks (`--cpu 68000` vs `--cpu 68020`) for representative array/pointer/struct patterns.
3. Document and enforce one canonical helper contract for indexed EA lowering.

Primary files:

- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`
- `docs/ARRAY_ACCESS_IMPLEMENTATION.md`

Exit criteria:

- Existing 68000 example baseline unchanged.
- Tests fail on accidental 68020 syntax in 68000 output.

## Phase 1: Full-Extension Indexed Addressing (Highest ROI)

Goal: support richer legal 68020 indexed forms and reduce fallback arithmetic.

Tasks:

1. Extend target capability model for 68020 full-extension support.
2. Expand lowering API to carry:
   - index size choice (`.w` or `.l`)
   - displacement width handling
   - extension metadata needed for legality checks
3. Emit full-extension forms in dynamic indexing paths where legal.
4. Keep 68000 path unchanged.

Primary files:

- `hasc/target.py`
- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`
- `hasc/codegen.py`

Tests/examples to add:

1. Struct-array field offsets outside brief displacement range.
2. Dynamic indexing with large effective displacements.
3. 1D/2D array access and address-of paths with nested expressions.

Exit criteria:

- `-m68020` assembly succeeds for new forms.
- Generated 68020 assembly uses fewer explicit scaling/arithmetic preludes where expected.
- 68000 output remains stable.

## Phase 2: `.w` Index Selection via Conservative Range Analysis

Goal: use `.w` index when proven safe, otherwise keep `.l`.

Tasks:

1. Add conservative range metadata from validation/type analysis.
2. Choose `.w` only when proof is strict (constants, bounded loops, safe casts).
3. Fall back to `.l` for all uncertain cases.

Primary files:

- `hasc/validator.py`
- `hasc/indexed_address.py`
- `hasc/codegen_indexed_address.py`
- `hasc/codegen.py`

Tests/examples to add:

1. Safe bounded loops over small arrays.
2. Signed boundary conditions around 16-bit limits.
3. Negative cases where `.w` must not be selected.

Exit criteria:

- No semantic regressions in index calculations.
- `.w` appears only in proven-safe cases.
- 68000 behavior unchanged.

## Phase 3: Memory-Indirect Addressing (Medium ROI)

Goal: add memory-indirect support for high-value patterns only.

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

## Phase 4: Targeted 68020 Instruction Substitutions (Optional)

Goal: selective wins after addressing improvements are stable.

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

## Phase 5: High-Value Follow-Ups (Planned)

Goal: close the remaining gaps that deliver measurable game-code wins, ordered
by payoff-to-risk. Each step is independently shippable, gated on its own
`TargetSpec` capability flag, and must leave `--cpu 68000` output byte-stable.

### 5.1 Unsigned 32-bit `mulu.l` / `divul.l` (smallest gap, highest certainty)

Status: implemented.

Problem: `TargetSpec.supports_32bit_muldiv` currently only drives the *signed*
forms (`muls.l`, `divsl.l`) in `hasc/codegen.py`. Unsigned operands
(`u8`/`u16`/`u32`/`UBYTE`/`UWORD`/`ULONG`) still take the signed 68020 path, so
`u32` values above `$7FFFFFFF` compute incorrectly on both targets, and the
68000 fallback still applies its signed 16-bit `_require_word_arith_operand()`
restriction.

Tasks:

1. Reuse the existing `CodeGen._is_unsigned_expr()` helper (already used for
   comparison lowering, `slo`/`sls`/`shi`/`shs`) to classify `*`, `/`, `%`.
2. When both operands classify as unsigned and `supports_32bit_muldiv` is set,
   emit `mulu.l` / `divul.l` instead of `muls.l` / `divsl.l`.
3. On the 68000 path, emit `mulu.w` / `divu.w` for the unsigned case and relax
   `_require_word_arith_operand()` to check the unsigned `0..65535` range
   rather than the signed range.
4. Mixed signed/unsigned operands keep the current signed lowering; record the
   decision in a comment rather than silently widening.

Primary files: `hasc/codegen.py`.

Tests/examples: extend `tests/test_codegen_68020_arithmetic.py` with unsigned
multiply/divide/modulo cases; add `examples/cpu68020_unsigned_muldiv.has`
exercising `u32` values above the signed 32-bit boundary.

Exit criteria: unsigned results correct on both targets; signed output for
existing examples unchanged on both targets.

Implementation notes:

- `CodeGen._is_unsigned_arith_pair()` gates the unsigned lowering. A
  non-negative integer literal is treated as signedness-neutral (representable
  in both domains) so `u32_value * 10` still takes the unsigned path, but at
  least one operand must be a declared unsigned value. A negative literal
  forces the signed path.
- The 68000 unsigned path uses `_require_unsigned_word_arith_operand()`, a
  sibling of `_require_word_arith_operand()`, so signed diagnostics are
  unchanged.
- Verified: `--cpu 68000` and `--cpu 68020` output for all existing
  `examples/*.has` is byte-identical to the pre-change output.

### 5.2 64-bit `muls.l`/`divs.l` forms and runtime Q16.16 operators

Problem: Q16.16 exists only as a compile-time literal conversion in
`hasc/parser.py` (`_const_to_q16()`); there is no runtime fixed-point operator
lowering at all. Games needing rotation, scaling, velocity integration, or
perspective division must hand-write inline assembly today.

The 68020 makes this cheap: `muls.l Dn,Dh:Dl` yields a full 64-bit product, and
`divs.l Dr,Dq:Dr` accepts a 64-bit dividend, so an exact Q16.16 multiply is
three instructions (multiply, shift the 64-bit result right by 16 across the
register pair, keep the low long) instead of a shift/mask approximation.

This is the largest item in Phase 5 and the only one that changes the language
surface, so it splits into two independently reviewable steps:

1. **Codegen capability first**: add `TargetSpec.supports_64bit_muldiv` and a
   lowering helper that emits the `Dh:Dl` register-pair forms. The register
   allocator must be able to reserve an adjacent scratch data register for the
   high half; extend `_muldiv_remainder_reg()` or add a sibling helper rather
   than hardcoding a pair.
2. **Language surface second**: decide how a Q16.16 *runtime type* is spelled
   (a distinct `q16` type is preferable to overloading `int`, because operator
   semantics differ and silent reinterpretation of `int` would be a breaking
   change). Then lower `*` and `/` on that type to the fixed-point sequence,
   with a documented 68000 fallback using `muls.w` partial products.

Do not start step 2 until step 1 is merged and tested in isolation.

Primary files: `hasc/target.py`, `hasc/register_allocator.py`,
`hasc/codegen.py`, then `hasc/parser.py`, `hasc/ast.py`, `hasc/validator.py`.

Tests/examples: precision tests comparing the 68000 fallback against the 68020
path for identical inputs (they must agree bit-for-bit, or the difference must
be documented); overflow and negative-operand boundary cases; an
`examples/q16_runtime_math.has` demo.

Exit criteria: identical numeric results on both targets for the supported
input range; no change to any program that does not use the new type.

### 5.3 Bitfield instructions (`bfextu`/`bfexts`/`bfins`/`bfffo`/`bfset`/`bfclr`/`bftst`)

Problem: packed-bit access currently lowers to shift/mask sequences on both
targets. The 68020 does this in one instruction against a memory operand.

High-value HAS patterns: HAM6 control-bit extraction, packed entity flags in
`struct Entity`, sprite attach/collision masks, and `bfffo` as a
single-instruction free-slot search over an entity-allocation bitmap.

Tasks:

1. Add `TargetSpec.supports_bitfield_ops`.
2. Identify the existing shift+mask emission sites (bitwise extract/insert on
   `struct` fields and on `&`/`|`/shift combinations with constant masks) and
   substitute the bitfield form only when offset and width are compile-time
   constants and the operand is a legal bitfield destination.
3. Leave every non-constant-mask case on the current path.

Primary files: `hasc/target.py`, `hasc/codegen.py`.

Tests/examples: constant-mask extract/insert on both targets producing equal
runtime values; a negative test asserting no bitfield instruction appears in
`--cpu 68000` output.

Exit criteria: measurable instruction-count reduction on the targeted patterns;
identical program behavior on both targets.

### 5.4 Instruction-cache-aware alignment

Problem: the 68020's 256-byte instruction cache and 32-bit bus reward 4-byte
alignment of loop tops, branch targets, and `long` data. HAS emits no alignment
directives today.

Tasks:

1. Add `TargetSpec.prefers_long_alignment` (true only for 68020).
2. Emit `cnop 0,4` before generated loop-head and branch-target labels when the
   flag is set.
3. Align `long`-typed entries in emitted data sections to 4 bytes.

Primary files: `hasc/target.py`, `hasc/codegen.py`.

Note: this is the first change that alters *label placement* rather than
instruction selection, so verify that no peephole rule in `hasc/peepholeopt.py`
matches across a newly inserted directive line.

Exit criteria: `--cpu 68000` output contains no new directives; `--cpu 68020`
output assembles cleanly under `-m68020` and program behavior is unchanged.

### Phase 5 dependency order

```
5.1 (done)
5.2 step 1 ──> 5.2 step 2   (strictly sequential; step 2 deferred, see below)
5.3, 5.4 ──> deferred indefinitely
```

### Post-5.1 reprioritisation (evidence from the game/demo corpus)

After 5.1 landed, the remaining items were re-assessed against the actual code
in `examples/games/` and `examples/demos/` rather than against the instruction
set in the abstract. The original ordering did not survive that check.

**5.2 is demoted to step 1 only.** `lib/math.s` already implements a software
`Q16Mul` using the exact `muls.w` partial-product approach proposed as the
68000 fallback, and `robots`, `caveride`, and `launchers` all declare the Q16
API via `extern func` - with **zero call sites** between them. The only
fixed-point physics in the repo (`examples/games/launchers/launchers.has`)
deliberately uses **8.8 in a plain `int`**, which needs no new type and no
64-bit multiply. 16 fractional bits only pay off for rotation, scaling, and
perspective, none of which exist here. The 68000 fallback costs roughly 450-550
cycles per multiply (~17% of a PAL frame at 50 multiplies), so a `q16` type
would be 68020-only in practice - a poor shape for the one item that changes
the language surface. Do step 1 (the `Dh:Dl` capability) because it is reusable
and capability-gated; revisit step 2 only when a demo needs rotation or scaling.

**5.3 is cut.** All four justifications fail against the corpus. Entity structs
(`bullet.has`, `player.has`, `launchers.has`) use one whole byte per flag, so
`move.b`/`tst.b` is already optimal and `bfextu` would be slower. HAM6 control
bits are decoded offline in the Python importer, not at runtime. A repo-wide
grep for mask patterns finds exactly one hit, in a documentation demo. And the
free-slot searches scan a byte field inside a strided struct array, which
`bfffo` cannot address without redesigning entity storage. The lowering would
never trigger on any code in this repository.

**5.4 is cut.** Compiler-generated loop bodies are ~110 instructions / 450+
bytes and overflow the 256-byte ICache every iteration regardless of head
alignment; aligning saves at most one prefetch on loop entry. The loops that
would benefit are hand-written `asm` blocks, which HAS emits verbatim and where
`cnop` insertion does not apply. Not worth taking regression risk in the
line-adjacent peephole matcher for a benefit in the noise floor.

### Higher-value work found during the 5.1 review (target-independent)

The 68020 is not the bottleneck in generated game code; the code generator is.
Measured against one `UpdateMissiles` loop iteration at `--cpu 68020`, each of
these outranks everything remaining in Phase 5, and each benefits stock 68000
most:

1. **68000 `ext.l` truncation in 32-bit multiply lowering** - the `ext.l`/`ext.l`
   pair before `muls.w` silently destroys the upper 16 bits of operands loaded
   as longs. Unlike the items below this is a correctness issue on the *default*
   target, currently masked only because affected values happen to fit a word.
2. **`dbra` + register-allocated loop counters.** Bounded `for` counters live in
   the stack frame and are reloaded and stored back every iteration - 6
   instructions and 4 memory accesses for what `dbra` does in one. The compiler
   emits no `dbra` anywhere.
3. **Loop-invariant hoisting / CSE for address computation.** `&entity[i]` is
   recomputed from scratch five times per iteration (~20 wasted instructions,
   ~20% of the loop). This also neuters Phase 1: a 32-byte stride falls back to
   `lsl.l #5`, so the scaled-index modes never engage on the very structures
   they were built for.
4. **Direct branch lowering for `&&`/`||` and comparisons** - replace the
   `slt`/`andi.l`/`neg.b`/`bne` materialise-then-test pattern and the `-(a7)`
   spills around immediate operands.
5. **`bra.s`/`bcc.s` short-displacement selection** where a byte displacement
   suffices.

### Known latent defect (prerequisite for any new numeric type)

`CodeGen._is_unsigned_expr` still classifies signedness as `not
ast.is_signed(type)`, an allowlist *complement*. 5.1 replaced this with an
explicit `UNSIGNED_ARITH_TYPES` allowlist for arithmetic, but comparison
lowering was deliberately left alone to keep that change output-neutral.

Today the bug is unreachable: `ast.is_signed()`'s enumeration happens to cover
every signed type currently declarable, and the types that fall through
(`ptr`, `APTR`, `bool`, `T*`) are ones where unsigned comparison is correct or
immaterial. But the classification is deny-by-omission, so the moment a `q16`,
`float`, `fixed`, or `i64` type is added to the type table without also editing
`is_signed()`, every `<`/`>`/`<=`/`>=` on it silently becomes an unsigned
branch. Harden `_is_unsigned_expr` to the same explicit allowlist (with an
explicit pointer branch) before starting 5.2 step 2. Expected to be
byte-identical on both targets today, so it is cheap to land and cheap to
verify.

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

1. Update feature behavior notes in `docs/ARRAY_ACCESS_IMPLEMENTATION.md`.
2. Update user-facing target notes in `docs/DEVELOPERS_GUIDE.md`.
3. Add user-visible changes to `docs/CHANGELOG.md`.
4. Include one minimal before/after assembly example in PR notes.

## Suggested Delivery Order

1. Phase 0 + Phase 1 together.
2. Phase 2 after Phase 1 stabilizes.
3. Phase 3 only if pattern-level wins are demonstrated.
4. Phase 4, one substitution at a time.
5. Phase 5 in the order 5.1, 5.3, 5.4 (any order, independent), then 5.2
   step 1, then 5.2 step 2.

## Definition of Done (Overall)

- 68020 support is materially improved for indexed addressing.
- 68000 default output and workflows remain stable.
- New behavior is documented, tested, and reproducible.
