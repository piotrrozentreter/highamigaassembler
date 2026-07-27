# hasc/codegen.py quirks and conventions (discovered while implementing Scc/DBcc fast paths)

## Parser: comparison operators are NOT all eagerly normalized
- `hasc/parser.py`'s `ASTBuilder` Transformer defines `le`, `gt`, `ge` (converts to `ast.BinOp`
  eagerly at parse time) but is **missing** `eq`, `ne`, `lt` methods.
- Result: `==`, `!=`, `<` comparisons remain raw `lark.Tree('eq'/'ne'/'lt', [left, right])`
  objects in the AST until some codegen function calls `self._normalize_expr(expr)` on them
  (this happens lazily, e.g. inside `_emit_expr`, `_emit_comparison_branch(_inverted)`).
- **Any new codegen-time AST analysis code must call `_normalize_expr` defensively** before
  inspecting a condition/expression, and even that doesn't cover every possible Tree shape
  (`normalize_expr` only converts recognized binop/unary rule names) - so a generic walker
  should also have a fallback that recurses into `node.children` when `hasattr(node,'data')
  and hasattr(node,'children')` (duck-typing for a raw Lark Tree).
- This caused a real bug: a "loop variable used in body?" AST walker missed `if (j == 2)`
  because `j == 2` was still a raw Tree, not a `VarRef`/`BinOp`. Fixed by normalizing +
  recursing into leftover Tree children in the walker itself.

## RegisterAllocator (hasc/register_allocator.py) is mostly decorative
- `self.reg_alloc` (`RegisterAllocator` instance) is barely consulted by real codegen.
  `_emit_expr`/`_emit_stmt` hardcode literal register names ("d0", "d1", "d2", occasionally
  "d3") throughout instead of calling `reg_alloc.allocate_data()`. Don't assume allocating a
  register via `RegisterAllocator` actually reserves it against the rest of codegen - it doesn't.
- **d7 is the one truly-reserved register**: never used as a scratch register anywhere in
  expression/statement codegen. It's compiler-wide reserved for `dbra` loop counters
  (`RepeatLoop`, and the `ForLoop` DBcc fast path). Validator/docs also treat d7 as reserved
  (can't `#pragma lockreg` it, etc.).
- Nested loops that both want d7 (e.g. `for` inside `for`, or `repeat` inside `for`) must
  save/restore d7 around the inner loop. See `CodeGen.dbra_depth` /
  `_dbra_loop_enter`/`_dbra_loop_exit` in codegen.py - a shared nesting-depth counter used by
  both `RepeatLoop` and the `ForLoop` dbra fast path so either can be "inner" or "outer".
  Note: this does NOT protect against a *called procedure* internally using a dbra loop while
  the caller is also mid-dbra-loop (d7 isn't saved across `jsr`/`rts`) - pre-existing gap,
  not fixed (would need prologue/epilogue-level d7 preservation, out of scope for a
  local codegen change).

## Peephole optimizer already does immediate-load downsizing
- `hasc/peepholeopt.py`'s `_optimize_immediate_ops` converts `move.l #n,dN` -> `moveq #n,dN`
  automatically when `-128 <= n <= 127`. Codegen should just always emit `move.l #imm,reg`
  for constant loads and let the peephole pass handle moveq/addq/subq downgrades - don't
  hand-roll that selection logic in codegen.py (existing convention, confirmed by grep: codegen.py
  never emits "moveq" itself).
- `peephole_optimize()` runs unconditionally at the end of `CodeGen.gen()` - no CLI flag to
  disable it, so test assertions on generated assembly always see the post-peephole form.

## gen() proc-label detection trick (useful for test tooling)
- `CodeGen.gen()` always emits `self.emit("")` (blank line) immediately before a procedure's
  own label (`f"{it.name}:"`). Internal branch labels (`for1:`, `endfor2:`, `else3:`, ...) are
  never preceded by a blank line. Use "label preceded by a blank line" to reliably slice out
  one procedure's assembly from the full output in tests, instead of matching `^\w+:$` alone
  (which also matches internal labels).

## Useful verification workflow: git worktree for before/after asm diffing
- `git worktree add ../some-baseline HEAD` gives a pristine checkout of the last commit in a
  sibling directory, without touching the current working tree's uncommitted changes. Compile
  the same `examples/*.has` files with both `python -m hasc.cli` (cwd = each worktree) and diff
  the `.s` outputs to confirm a codegen change only affects the intended cases. Clean up
  afterwards with `git worktree remove <path> --force`.
- No `vasm`/`vasmm68k_mot` toolchain is installed in this dev environment (Windows) - assembly
  validation here relies on manual instruction-level review + the diff-against-baseline
  technique above, not actually invoking the assembler.

## Misc
- `ast.py` dataclasses have NO `line` field (contrary to what some docs/tips assume) - can't
  cite source line numbers from AST nodes directly in codegen-level errors here.
- `Assign.target` is a plain `str` for scalar variables (not wrapped in `VarRef`); only
  `ArrayAccess`/`MemberAccess` targets are AST nodes. Check `isinstance(target, str)` to
  detect "plain scalar assignment".
