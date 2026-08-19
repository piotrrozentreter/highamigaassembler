# CPU 68020 Implementation Plan

Status: planning document for incremental 68020 support in HAS

## Purpose

Provide a practical, low-risk roadmap for expanding 68020 support while preserving default 68000 behavior and compatibility.

## Current Baseline

- `--cpu` supports `68000` and `68020`, default is `68000`.
- 68020 support currently focuses on scaled indexed addressing.
- Full-extension indexed addressing, memory-indirect modes, and `.w` index selection are deferred.

## Non-Goals (for now)

- Broad "replace everything with 68020 instructions" passes.
- Rare or privileged/system-oriented instructions without clear language/runtime need (for example: `CALLM`, `RTM`, `MOVEC`, `CAS2`).

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
4. Phase 4 last, one substitution at a time.

## Definition of Done (Overall)

- 68020 support is materially improved for indexed addressing.
- 68000 default output and workflows remain stable.
- New behavior is documented, tested, and reproducible.
