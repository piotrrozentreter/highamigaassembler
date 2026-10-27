# HAS Compiler Developer's Guide

This guide describes the compiler as it exists in the repository: its pipeline,
the responsibilities of its main modules, target-dependent code generation, and
the test workflow for compiler changes. For user-facing syntax and language
examples, see the [HAS Developer's Guide](DEVELOPERS_GUIDE.md). For setup and
release packaging, see [Contributing](CONTRIBUTING.md) and
[Installation](INSTALL.md).

## Contents

- [Compiler architecture](#compiler-architecture)
- [Development setup and checks](#development-setup-and-checks)
- [Compilation pipeline](#compilation-pipeline)
- [Parser and validator](#parser-and-validator)
- [Code generation and register management](#code-generation-and-register-management)
- [Indexed addressing and CPU targets](#indexed-addressing-and-cpu-targets)
- [Register intrinsics](#register-intrinsics)
- [Adding or changing a feature](#adding-or-changing-a-feature)
- [Tests and regression checks](#tests-and-regression-checks)
- [Related references](#related-references)

## Compiler architecture

HAS translates its assembly-oriented language into Motorola 68000-family
assembly. The default target is 68000; `--cpu 68020` opts into selected 68020
instructions and addressing modes. The generated assembly is intended for
`vasm`; optional executable and ADF creation additionally invokes `vlink` and,
for ADF images, `amitools`/`xdftool`.

The compiler package is organized around these responsibilities:

| Module | Responsibility |
| --- | --- |
| `hasc/cli.py` | Command-line options, pipeline orchestration, assembly metadata, optional host build |
| `hasc/parser.py` | Preprocessing, Lark grammar, AST construction |
| `hasc/ast.py` | AST node definitions and type helpers |
| `hasc/validator.py` | Symbol, declaration, expression, and semantic checks; resolved dimensions |
| `hasc/codegen.py` | Assembly emission, procedure frames, expressions, statements, and target plumbing |
| `hasc/target.py` | Closed CPU target model and target capabilities |
| `hasc/indexed_address.py` | Target-aware indexed effective-address lowering |
| `hasc/codegen_indexed_address.py` | Adapters for array, pointer, struct, and address-of code paths |
| `hasc/register_allocator.py` | Scratch-register allocation and spill tracking used by code generation |
| `hasc/macro_expander.py` | Macro collection, expansion, and parameter substitution |
| `hasc/reachability.py` | Conservative opt-in removal of unreachable internal procedures |
| `hasc/peepholeopt.py` | Post-generation assembly rewrites and branch-size selection |
| `hasc/asset_import.py` | `#import` dispatch and generated-asset metadata |
| `hasc/amiga_toolchain.py` | Optional vasm/vlink executable and bootable ADF workflow |

Other compiler-adjacent material lives in `tests/`, `examples/tests/`,
`tools/`, `lib/`, and `scripts/`. Keep implementation claims tied to these
sources and tests rather than line numbers, which change frequently.

## Development setup and checks

From a checkout, install the project dependencies and run the compiler through
the current Python environment:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m hasc.cli examples/add.has -o /tmp/add.s
```

The installed `hasc` command is the public CLI equivalent. Use `hasc --help`
for the authoritative option list. The positional input argument remains
required when using `--generate`; its file contents are ignored in that mode.
External generation runs a Python script and parses its standard output as HAS.
Inline `@python` generation is a separate, procedure-local feature; see
[Compile-Time Python Integration](PYTHON_INTEGRATION.md).

The compiler can produce assembly without the Amiga toolchain. `--exe` and
`--adf` invoke external tools after successful compilation; those tools are not
bundled with HAS. See [Installation](INSTALL.md) for prerequisites.

## Compilation pipeline

The main orchestration is in `hasc/cli.py`:

1. Parse options and create the selected `TargetSpec`.
2. Read the input file, or run the `--generate` script and capture stdout.
3. Call `parser.parse()`. Preprocessing handles includes, conditional
   compilation, and asset imports before HAS syntax is parsed.
4. Unless `--no-validate` is given, run `Validator.validate()` and then
   `Validator.apply_resolutions()` to place validated constant dimensions and
   sizes on the AST for code generation.
5. Apply `reachability.strip_unused_procs()` when either unused-procedure
   option is active. The pass is conservative and opt-in.
6. Construct `CodeGen` with the selected target and emit assembly.
7. Write a version/timestamp preamble and, by default, a build-statistics
   comment block. `--no-asm-stats` suppresses the statistics block.
8. If requested, pass the output through the host toolchain for an executable
   and/or bootable ADF.

This order matters. Asset import may create `.s` fragments that code generation
adds as vasm `INCLUDE` directives. Reachability runs after validation so it can
analyze resolved procedure declarations, but before assembly generation.

## Parser and validator

### Parser

The grammar is defined in `hasc/parser.py` as `GRAMMAR`; `ASTBuilder` converts
Lark parse trees into the dataclasses in `hasc/ast.py`. The parser's
preprocessing path also expands `#include`, `#ifdef`/`#ifndef`, comparison
`#if`, and `#import` directives. Keep syntax changes in the grammar and
transformer consistent, and verify both valid and invalid source forms.

The AST is not the final semantic record for every value: validation maintains
symbol/type information, then `apply_resolutions()` applies validated constant
array dimensions and sizes where code generation expects them. Do not rely on
the old blanket rule that validation never mutates the AST; the current CLI
deliberately applies these resolutions after validation succeeds.

### Validator

`Validator` gathers declarations and validates references, types, procedure
signatures, arrays, pragmas, and supported expression/statement forms. It
raises `ValidationError` for invalid HAS input and returns warnings for
non-fatal issues. `--no-validate` bypasses this stage and is intended for
specialized debugging, not as a normal workaround for invalid programs.

When adding a semantic rule, make its diagnostic identify the source construct
and, where available, its source line. Check that the rule agrees with the
language guide and with code generation; validating a form that codegen cannot
emit is not sufficient.

## Code generation and register management

`CodeGen` in `hasc/codegen.py` owns output generation, procedure setup and
teardown, statement and expression lowering, and access to target capabilities.
Reusable indexed-address construction belongs in
`hasc/indexed_address.py`; call-site evaluation order and operand loads/stores
belong in `hasc/codegen_indexed_address.py`.

The compiler has an active `RegisterAllocator` instance. It manages scratch
data registers `d0`–`d6` and address registers `a0`–`a2`; `d7` is kept for
`dbra`/DBcc loop counters, `a6` is used as a frame register where applicable,
and `a7` is the stack pointer. Code generation also has fixed scratch-register
conventions and explicit stack preservation in particular paths, so the
allocator is not a claim that every emitted register use is dynamically
allocated.

Temporary allocations must be released on all code paths. When code spills,
restore spills in reverse order and keep the spill depth balanced. CodeGen
resets allocator state at procedure entry and checks that no temporary or spill
remains at procedure exit. The `#pragma lockreg(...)` setting excludes locked
registers from the allocator's eligible scratch sets; it does not save or
preserve a register across calls, and it cannot turn arbitrary registers into
callee-saved registers.

The procedure ABI is HAS-specific. Default arguments are passed on the stack;
`__reg(...)` annotations in known procedure signatures select register
parameters. Non-native HAS procedures save register parameters into their
frames before ordinary code can clobber them. Native procedures are intended
for bodies that explicitly manage their register-level contract. For external
interfaces, match the actual library or assembly routine's declaration and
register/stack convention; do not describe the convention as a universal
Motorola or AmigaOS ABI.

### Register intrinsics

`GetReg("register")` and `SetReg("register", value)` are parsed and validated
as compiler intrinsics, not library calls. Validation currently accepts `d0`
through `d7` and `a0` through `a3`. `GetReg` reads a longword into the
expression result. `SetReg` evaluates its value, writes the selected register,
and can be used as an expression (its result is the value written). The
intrinsics emit ordinary `move.l` operations and are CPU-neutral for both
`--cpu 68000` and `--cpu 68020`; callers remain responsible for register
liveness and ABI effects.

## Indexed addressing and CPU targets

`--cpu 68000` is the default and does not emit 68020-only indexed forms.
`--cpu 68020` enables the capabilities recorded in `hasc/target.py`; generated
68020 output must be assembled with `vasmm68k_mot -m68020`, not `-m68000`.
The source language and data layout are shared between the targets, but code
generation is not identical.

For dynamic array, typed-pointer, struct-array, two-dimensional, and
address-of indexing, codegen routes through the indexed-address helpers.
Constant indexes may be folded to direct offsets. On 68000, element strides
are calculated with compatible shifts or multiply/fallback sequences; there is
no scaled-index syntax. On 68020, supported scale factors `2`, `4`, and `8`
can be encoded in the indexed operand. The 68020 path also supports
full-extension indexed displacements outside the brief signed-byte range.
Memory-indirect indexed addressing is not enabled.

An index-size `.w` operand is only used on 68020 paths that prove the original
index is a constant in the signed 16-bit range; other cases retain `.l`.
Arbitrary strides can require explicit multiplication: strides that fit the
word immediate range use `mulu.w` on 68000 and `mulu.l` on 68020, while large
strides use full-width shift/add lowering. Which specific operand form appears
depends on the access path and displacement. Never generalize the 68020
instruction selection to the default 68000 target.

Other verified target differences include 68020 long multiply/divide forms,
`extb.l` sign extension, long branches when a branch exceeds the word range,
and preferred four-byte alignment for long/pointer data labels. Branch
shortening to `.s` is target-neutral. Signed and unsigned multiply/divide
behavior, range diagnostics, and implementation phase status are described in
the [operator reference](OPERATORS.md) and
[68020 implementation plan](CPU_68020_IMPLEMENTATION_PLAN.md).

### Array and pointer access invariants

- Primitive global arrays support up to two dimensions; struct-array member
  access is one-dimensional. There are no runtime bounds checks.
- Narrow array and typed-pointer reads must extend or clear the destination
  according to the element type before the value is consumed. The shared
  `emit_narrow_element_load()` helper centralizes that rule.
- Index expressions may call procedures. Evaluate them before relying on an
  address scratch that the call might clobber; stores evaluate the right-hand
  side before constructing the final destination address.
- 68020 `.w` index selection is conservative and applies only when both the
  path supports scaled addressing and the original index is a compile-time
  signed-16-bit constant.

These are enforced by `tests/test_codegen_basic.py`,
`tests/test_codegen_68020_indexing.py`, and
`tests/test_narrow_element_reads.py`.

## Adding or changing a feature

For a language or code-generation change, work through the affected layers:

1. Define the syntax and semantics, including error cases and target scope.
2. Update the grammar/transformer and AST only if the feature needs new syntax
   or representation.
3. Add validation and diagnostics for semantic constraints.
4. Implement code generation with explicit register, evaluation-order, and
   68000/68020 legality decisions.
5. Add a focused test and a realistic `.has` example. Include both CPU targets
   when codegen may differ, and negative cases for rejected input.
6. Update the canonical user guide or technical guide and record user-visible
   behavior in `docs/CHANGELOG.md`.

For assembly-related changes, inspect generated assembly and, when available,
assemble it with the matching vasm CPU flag. An example compiling successfully
does not by itself prove that generated instructions are legal for the selected
CPU.

## Tests and regression checks

Run focused tests first, then the full suite when practical:

```bash
python -m pytest tests/test_codegen_basic.py \
  tests/test_codegen_68020_indexing.py \
  tests/test_narrow_element_reads.py
python -m pytest
```

The example split gate checks expected-success and expected-failure compiler
examples:

```bash
./scripts/tests/test_examples_split.sh
```

For a quick target comparison, compile an example twice:

```bash
python -m hasc.cli examples/tests/compiler/array_access_test.has \
  --cpu 68000 -o /tmp/array-68000.s
python -m hasc.cli examples/tests/compiler/array_access_test.has \
  --cpu 68020 -o /tmp/array-68020.s
```

When vasm is installed, assemble each output with the matching CPU option:

```bash
vasmm68k_mot -m68000 -Fhunkexe -o /tmp/array-68000.o /tmp/array-68000.s
vasmm68k_mot -m68020 -Fhunkexe -o /tmp/array-68020.o /tmp/array-68020.s
```

`docs/CONTRIBUTING.md` lists the repository's broader checks, including the
VBCC interop regression scripts.

## Related references

- [HAS Developer's Guide](DEVELOPERS_GUIDE.md) — syntax and practical examples
- [Operator Reference](OPERATORS.md) and [Bitwise Operators](BITWISE.md)
- [Struct Pointers](STRUCT_POINTERS.md)
- [CPU 68020 Implementation Plan](CPU_68020_IMPLEMENTATION_PLAN.md)
- [Python Integration](PYTHON_INTEGRATION.md)
- [Contributing](CONTRIBUTING.md) — code review and test workflow
- [CHANGELOG](CHANGELOG.md) — user-visible releases and compatibility notes
