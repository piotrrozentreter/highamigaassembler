---
name: python-compiler-engineering
description: 'Python engineering patterns and best practices for building/maintaining the HAS compiler internals (parser.py, ast.py, validator.py, codegen.py, register_allocator.py, peepholeopt.py). Use when writing or refactoring compiler Python code, not just fixing a single bug.'
argument-hint: 'Describe the compiler module being changed (parser/validator/codegen/allocator/optimizer) and whether this is new code, a refactor, or a bug fix.'
user-invocable: true
---

# Python Engineering for Compiler Internals

Idiomatic-Python patterns for writing maintainable, correct compiler code in `hasc/`. This complements
[compiler-python.instructions.md](../../instructions/compiler-python.instructions.md), which covers
project-specific correctness rules (register lifecycle, ABI, CPU targets). This skill covers *how* to
write the Python itself.

## When to Use

- Adding a new AST node, pass, or pipeline stage (not a one-line bug fix).
- Refactoring dispatch logic (`_emit_stmt`, `_validate_expr`, etc.) that is growing long `if/elif` chains.
- Introducing new symbol-table or state-tracking structures.
- Reviewing whether existing compiler Python code follows solid engineering patterns.

## Core Patterns

### 1. Dispatch: prefer dict/`singledispatch` over long `if/elif` chains
Existing code uses `isinstance`-based `if/elif` dispatch in `_emit_stmt`/`_validate_expr`. This is
acceptable for small counts, but once a dispatch chain exceeds ~6-8 branches, prefer a dispatch table:
```python
def _emit_stmt(self, stmt):
    handler = self._stmt_handlers.get(type(stmt))
    if handler is None:
        raise CodeGenError(f"No handler for statement type {type(stmt).__name__}", stmt.line)
    return handler(self, stmt)

_stmt_handlers = {
    ast.IfStmt: _emit_if,
    ast.WhileLoop: _emit_while,
}
```
Benefits: O(1) dispatch, forces every node type to be handled explicitly (missing entries fail loudly
instead of falling through to a silent `else` branch), and is easy to introspect/test in isolation.
Only refactor existing dispatch chains when already touching that function for the task at hand -
do not do drive-by refactors.

### 2. AST nodes: dataclasses, immutability by convention, no transient state
- Keep `@dataclass` nodes as pure data carriers with `line: int` for diagnostics.
- Never add mutable "scratch" fields to AST nodes for validator/codegen bookkeeping (violates
  Pitfall #3 in the workspace instructions). Instead, key metadata by `id(node)` or by a stable
  node identity in an external dict owned by the pass that needs it (e.g. `self.expr_types: dict[int, Type]`).
- Consider `frozen=True` for nodes that must never be mutated after construction (e.g. resolved
  literal/const nodes); use `field(default_factory=list)` instead of mutable default arguments for
  any list/dict-valued fields.

### 3. Symbol tables and multi-pass state
- Two-pass validation (collect symbols, then validate) should use plain dicts/`ChainMap` for scoped
  lookups rather than ad-hoc class attributes scattered across methods.
- Use `ChainMap` or an explicit scope-stack list for nested scopes (proc locals shadowing globals)
  instead of manually saving/restoring dict entries.
- Prefer explicit `Enum` types for closed sets (opcode categories, register classes, CPU targets)
  over bare strings - this lets `mypy`/type checkers and IDE tooling catch invalid values, and gives
  you exhaustiveness checks when combined with dispatch tables.

### 4. Register allocator: encapsulate state, make invariants checkable
- Keep allocation/free symmetric and centralize it: avoid duplicating "if free, allocate; else spill"
  logic at each call site. A single `allocate_data()`/`free()` pair with internal bookkeeping (e.g. a
  `set`/bitmask of in-use registers) is easier to audit than scattered manual tracking.
- Add a cheap internal assertion/consistency check (e.g. "all registers freed at end of proc emission")
  that can be enabled during development to catch leaks immediately rather than downstream in generated
  assembly.
- Prefer context-manager style helpers for scoped allocation when a register's lifetime matches a
  clear block (`with self.reg_allocator.data() as r: ...`) IF this fits the existing calling style;
  don't force a rewrite of unrelated allocation code to introduce this pattern.

### 5. Error handling
- Raise specific exception types (`CodeGenError`, validator `self.error(...)`) with line numbers -
  never swallow exceptions with bare `except:` or `except Exception: pass` in pipeline stages.
- Fail fast on invariant violations (e.g. unknown AST node type, missing symbol table entry) rather
  than defaulting to a silent fallback that could mask a real bug in generated assembly.

### 6. Testing and validation patterns
- Golden-file / snapshot testing: for codegen/peephole changes, compare generated `.s` output against
  a known-good baseline (see `regression-sweep` skill) rather than hand-asserting individual lines.
- For parser/validator changes, write both a valid-path and an invalid-path `.has` example - assert
  the invalid one produces the expected error message/line, not just "raises something."
- Keep pytest-based unit tests (see `tests/`) focused on pure functions (e.g. helpers in
  `codegen_utils.py`, `target.py` capability checks) where inputs/outputs are easy to assert without
  needing a full compile pipeline.

### 7. Performance and recursion
- AST traversal is typically recursive; for deeply nested expressions this can hit Python's recursion
  limit. Prefer explicit worklist/stack-based traversal over recursion in hot paths that may process
  deeply nested or generated expressions (e.g. macro-expanded or large array-initializer expressions).
- Avoid quadratic patterns in symbol lookup or peephole passes (e.g. repeated linear scans over the
  full instruction list per optimization); prefer indexed lookups (dict by label/register) when the
  instruction count can grow large (large `proc` bodies, unrolled loops).

### 8. General Python hygiene for this codebase
- Type hints on new/modified function signatures, especially pipeline entry points (`parse()`,
  `validate()`, `generate()`) - improves IDE/AI navigation of the 2800+ line `codegen.py`.
- No mutable default arguments (`def f(x, seen=[])` -> `def f(x, seen=None): seen = seen or []`).
- Use f-strings for error/diagnostic messages, not `%`-formatting or manual concatenation.
- Keep functions focused: if an `_emit_*`/`_validate_*` method exceeds roughly 60-80 lines and mixes
  multiple concerns (e.g. type-checking AND code emission), consider extracting a helper - but only
  when already modifying that function for the task, not as a standalone refactor.

## Non-Goals

- This skill does not cover 68000/68020 assembly correctness (see `assembly-validator` skill).
- This skill does not replace the mandatory correctness rules in
  [compiler-python.instructions.md](../../instructions/compiler-python.instructions.md) - those rules
  win in case of any apparent conflict.
- Do not use this skill to justify large speculative refactors; apply patterns incrementally,
  scoped to the task at hand (see workspace-wide "Minimal invasive edits" rule).

## References

- Project workspace conventions: [../../copilot-instructions.md](../../copilot-instructions.md)
- Compiler Python correctness rules: [../../instructions/compiler-python.instructions.md](../../instructions/compiler-python.instructions.md)
- Regression validation workflow: [../regression-sweep/SKILL.md](../regression-sweep/SKILL.md)
