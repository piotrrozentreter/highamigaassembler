# Codegen Tips: Scc Boolean Assignment and DBcc Loop Optimisation

These are two codegen improvements left out of the 2025 peephole pass because
they require AST-level analysis that cannot be done safely at the assembly text
level.  Both changes belong in `hasc/codegen.py`.

---

## 1  Branchless Boolean Assignment via `Scc`

### Current situation

Scc instructions are **already used** for comparison-expression results
(lines ~1079, ~1239, ~1250 in `codegen.py`).  The existing pattern is:

```asm
    cmp.l  d1,d0
    seq    d0          ; $FF if equal, $00 if not
    andi.l #$FF,d0     ; zero-extend
    neg.b  d0          ; $01 if equal, $00 if not
```

The **new peephole pass** (`_eliminate_tst_after_andi_neg`) already removes the
redundant `tst.l d0` that used to follow this sequence.

### Remaining gap: `if/else` that assigns 0 or 1

When a user writes an explicit boolean assignment via an `if` statement:

```has
if a > b {
    flag = 1
} else {
    flag = 0
}
```

the current `_emit_stmt` (IfStmt branch, ~line 2576) generates the branchy version:

```asm
    ; evaluate (a > b) into d0
    cmp.l d1,d0
    ble   .else_1
    move.b #1,-6(a4)
    bra   .endif_1
.else_1:
    move.b #0,-6(a4)
.endif_1:
```

This can become two fewer instructions using Scc:

```asm
    ; evaluate (a > b) → flags already set by cmp
    sgt  d0            ; d0 = $FF if gt, $00 if not
    neg.b d0           ; d0 = $01 if gt, $00 if not
    move.b d0,-6(a4)
```

### How to implement

Inside `_emit_stmt`, **before** the general IfStmt path, add a fast-path check:

```python
def _is_bool_assign_01(stmt):
    """True if stmt is  var = 1  or  var = 0  (integer literal)."""
    return (
        isinstance(stmt, ast.Assign)
        and isinstance(stmt.value, ast.Number)
        and stmt.value.value in (0, 1)
    )

def _emit_bool_assign_scc(self, stmt, params, locals_info, proc, indent, frame_reg):
    """
    Fast path for:   if <comparison> { var = 1 } else { var = 0 }
    (and the inverted form with 1/0 swapped).

    Emits:  <comparison flags>; Scc dN; neg.b dN; move.b dN,<var>
    """
    cond = stmt.cond
    then1 = stmt.then_body
    else0 = stmt.else_body

    # Must be exactly one assignment in each branch, same variable, values 1 and 0.
    if (
        len(then1) == 1 and _is_bool_assign_01(then1[0])
        and len(else0) == 1 and _is_bool_assign_01(else0[0])
        and then1[0].name == else0[0].name
    ):
        then_val  = then1[0].value.value
        else_val  = else0[0].value.value
        var_name  = then1[0].name

        if {then_val, else_val} != {0, 1}:
            return False  # not a proper boolean assignment

        invert = (then_val == 0)   # then=0,else=1 → use inverted condition

        # Try to emit flags via _emit_comparison_branch_inverted / _emit_comparison_branch.
        # We need the Scc mnemonic that matches the comparison.
        scc_map = {
            '==': 'seq', '!=': 'sne',
            '<':  'slt', '<=': 'sle',
            '>':  'sgt', '>=': 'sge',
        }
        if not (isinstance(cond, ast.BinOp) and cond.op in scc_map):
            return False  # condition not a simple comparison; fall back

        # Evaluate both sides, emit cmp
        code  = self._emit_expr(cond.left,  params, locals_info, "d0", "d1",
                                target_type=None, frame_reg=frame_reg)
        code += self._emit_expr(cond.right, params, locals_info, "d1", "d2",
                                target_type=None, frame_reg=frame_reg)
        code.append(f"    cmp.l d1,d0")

        scc   = scc_map[cond.op]
        if invert:          # invert condition: sgt → sle, etc.
            inv = {'seq':'sne','sne':'seq','slt':'sge','sge':'slt','sle':'sgt','sgt':'sle'}
            scc = inv[scc]

        code.append(f"    {scc} d0")
        code.append(f"    neg.b d0    ; $FF -> $01, $00 -> $00")

        # Find the destination variable and emit store
        local_info = next((l for l in locals_info if l[0] == var_name), None)
        if not local_info:
            return False
        _, vtype, offset = local_info
        size   = ast.type_size(vtype) if vtype else 4
        suffix = ast.size_suffix(size)
        code.append(f"    move{suffix} d0,{-offset}({frame_reg})")

        for line in code:
            self.emit(line if line.startswith(indent) else indent + line.lstrip())
        return True

    return False
```

Then in `_emit_stmt`, insert **before** the general IfStmt code:

```python
elif isinstance(stmt, ast.IfStmt):
    # Fast path: branchless boolean assignment
    if stmt.else_body and self._emit_bool_assign_scc(
            stmt, params, locals_info, proc, indent, frame_reg):
        return
    # ... existing general path ...
```

### Caveats and risks

* Only activate when `stmt.else_body` is present and both branches contain exactly
  one assignment to the **same** variable.
* Handle pointer / address register variables with care: `Scc` only works on data
  registers.  Guard with `vtype not in pointer_types`.
* Unsigned comparisons need `sls`/`shi`/`slo`/`shs` — extend `scc_map` accordingly
  (mirror what the existing `_emit_expr` BinOp path does at ~line 1250).
* Add a regression compile of `examples/operators_test.has` after the change; the
  existing test suite (`tests/test_peepholeopt.py`) validates the peephole layer.

---

## 2  `DBcc` Counter Loop for `ForLoop`

### Current situation

`RepeatLoop` already emits `dbra` correctly (lines ~2790-2810).
`ForLoop` does not — it emits a generic compare-branch pattern:

```asm
for1:
    move.l -12(a4),d0
    moveq  #31,d1
    cmp.l  d1,d0
    bgt    endfor2
    ; ... body ...
forcont3:
    moveq  #1,d1
    move.l -12(a4),d0
    add.l  d1,d0
    move.l d0,-12(a4)
    bra    for1
endfor2:
```

Per-iteration cost (excluding body): 3 load/store + cmp + branch + 3 load/store + add = ~9 instructions.

With `dbra` the loop-control cost is **1 instruction**.

### Conditions required for `dbra` substitution

All of the following must hold:

| # | Condition | How to check in codegen |
|---|-----------|------------------------|
| 1 | `stmt.start` is the constant `0` | `isinstance(stmt.start, ast.Number) and stmt.start.value == 0` |
| 2 | `stmt.end`   is a non-negative integer constant ≤ 32767 | `isinstance(stmt.end, ast.Number) and 0 <= stmt.end.value <= 32767` |
| 3 | `stmt.step`  is the constant `1` | `isinstance(stmt.step, ast.Number) and stmt.step.value == 1` |
| 4 | Loop variable is **not read or written** inside the body | AST walk — see helper below |
| 5 | A scratch data register is available (d7 or any free Dn) | Check `self.reg_allocator` |

### Helper: check whether loop variable appears in body AST

```python
def _var_used_in_body(self, var_name, body):
    """Return True if var_name appears as a VarRef (read) anywhere in body stmts."""
    import hasc.ast as ast_mod

    def _walk(node):
        if isinstance(node, ast_mod.VarRef) and node.name == var_name:
            return True
        for child in vars(node).values():
            if isinstance(child, list):
                if any(_walk(c) for c in child if isinstance(c, ast_mod.ASTNode)):
                    return True
            elif isinstance(child, ast_mod.ASTNode):
                if _walk(child):
                    return True
        return False

    return any(_walk(s) for s in body)
```

> **Note**: `ast.ASTNode` may not exist as a base class in the current codebase.
> Adapt `_walk` to iterate over `dataclasses.fields(node)` instead if needed.

### Proposed `dbra` code path inside `_emit_stmt` → ForLoop

```python
elif isinstance(stmt, ast.ForLoop):
    start_label = self._next_label("for")
    end_label   = self._next_label("endfor")
    cont_label  = self._next_label("forcont")
    self.loop_stack.append((cont_label, end_label))

    # --- DBra fast path ---------------------------------------------------
    use_dbra = (
        isinstance(stmt.start, ast.Number) and stmt.start.value == 0
        and isinstance(stmt.end,   ast.Number) and 0 <= stmt.end.value <= 32767
        and isinstance(stmt.step,  ast.Number) and stmt.step.value == 1
        and not self._var_used_in_body(stmt.var, stmt.body)
    )

    if use_dbra:
        count = stmt.end.value + 1          # for i=0 to N → N+1 iterations
        dbra_reg = self.reg_allocator.allocate_data()   # grab a free Dn

        # Load counter (count-1) into dbra_reg — dbra counts N+1 times from N
        self.emit(indent + f"moveq #{count - 1},{dbra_reg}")
        self.emit(f"{start_label}:")

        for s in stmt.body:
            self._emit_stmt(s, params, locals_info, proc, indent, is_void,
                            frame_reg=frame_reg)

        self.emit(f"{cont_label}:")
        self.emit(indent + f"dbra {dbra_reg},{start_label}")
        self.emit(f"{end_label}:")

        self.reg_allocator.free(dbra_reg)
        self.loop_stack.pop()
        return   # skip the general path below
    # ----------------------------------------------------------------------

    # ... existing general ForLoop code path unchanged ...
```

### What the output looks like

Before (for `for i = 0 to 31`):
```asm
    move.l #0,-12(a4)    ; i = 0
for1:
    move.l -12(a4),d0
    moveq  #31,d1
    cmp.l  d1,d0
    bgt    endfor2
    ; body
forcont3:
    moveq  #1,d1
    move.l -12(a4),d0
    add.l  d1,d0
    move.l d0,-12(a4)
    bra    for1
endfor2:
```

After:
```asm
    moveq  #31,d7         ; loop counter (31+1 = 32 iterations)
for1:
    ; body
forcont3:
    dbra   d7,for1
endfor2:
```

Loop-control instructions per iteration: **8 → 1**.

### Caveats and risks

* **`dbra` is a 16-bit decrement**: counter wraps from 0 to −1 (not from 0 to 65535).
  The guard `count <= 32767` ensures the word counter never wraps incorrectly.
* **`count = 0`**: If `stmt.end.value == -1` (i.e., `for i = 0 to -1`), the loop
  should execute 0 times.  `dbra` with initial value `−1` would execute 65536 times —
  fall back to the general path if `stmt.end.value < 0`.
* **Register allocator**: call `allocate_data()` and `free()` symmetrically on every
  control-flow path (including the `break` path through `end_label`).  Do not
  hardcode `d7` — the allocator picks the least-clobbered register.
* **`break` / `continue` still work**: `cont_label` sits just before `dbra`, so
  `continue` → decrement and re-test.  `break` → jump to `end_label` past `dbra`.
* Test with `examples/break_continue_test.has` after the change.
* Run the full example suite afterward:
  ```
  python -m hasc.cli examples/<each>.has -o /tmp/test.s
  ```

---

## Testing checklist after implementing either change

- [ ] `python tests/test_peepholeopt.py` — all 43 tests still pass
- [ ] `examples/break_continue_test.has` compiles and loop counts are correct
- [ ] `examples/operators_test.has` — boolean expression results unchanged
- [ ] `examples/random_test.has` — conditional branches unchanged
- [ ] Full suite: 63 examples compile with zero new failures
