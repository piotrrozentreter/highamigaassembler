# Array Access Implementation Summary

## Changes Made

### 1. AST Extension (`hasc/ast.py`)
- Added `ArrayAccess` dataclass to represent array indexing operations
- Supports both 1D (`arr[i]`) and 2D (`matrix[row][col]`) array access

### 2. Grammar Extension (`hasc/parser.py`)
- Added grammar rule: `CNAME ("[" expr "]")+ -> array_access`
- Allows arbitrary expressions as array indices
- Supports chained subscripts for multidimensional arrays

### 3. Parser Transformer
- Implemented `array_access()` transformer in `ASTBuilder`
- Creates `ArrayAccess` nodes with name and list of index expressions

### 4. Code Generation (`hasc/codegen.py`)

#### Array Dimension Tracking
- Added `_build_array_dimensions()` to collect global array dimensions
- Stores dimensions in `self.array_dims` dictionary

#### 1D Array Access
```m68k
lea arrayname,a0           ; Load base address
move.l index_expr,d1       ; Evaluate index
lsl.l #2,d1                ; Multiply by 4 (element size)
move.l (a0,d1.l),d0        ; Load element
```

The 68000 sequence above is the compatibility baseline. With `--cpu 68020`,
dynamic accesses use the 68020 scaled form for supported strides:

```m68k
lea arrayname,a0
move.l index_expr,d1
move.l (a0,d1.l*4),d0      ; long/int element
```

The same lowering is used for primitive 1D reads and stores, typed-pointer
reads and stores, struct-array member access, two-dimensional reads and stores,
and address-of operations. The shared `hasc/indexed_address.py` helper returns
both any required prelude instructions and the final indexed operand; wrappers
in `hasc/codegen_indexed_address.py` keep each code-generation path on that
contract.

### CPU-dependent lowering

The CLI accepts `--cpu 68000` and `--cpu 68020`, defaulting to `68000`. Index
registers are long-sized (`dN.l`) by default. Scale factors `2`, `4`, and `8` are
emitted only for 68020-capable paths; scale `1` is represented by the ordinary
unscaled indexed operand. Constant indexes continue to use direct constant
offsets.

Under `--cpu 68020`, `index_fits_word_range()` in `hasc/indexed_address.py`
checks whether an index expression is a compile-time constant fitting the
signed 16-bit range (-32768..32767). When true, `lower_indexed_address()` uses
a `.w`-sized index register (e.g. `4(a0,d1.w*8)`) instead of `.l` (e.g.
`4(a0,d1.l*8)`), a smaller/faster operand. This is applied at four call sites
in `hasc/codegen_indexed_address.py`: struct-array member read and store,
array store, and typed-pointer store. Typed-pointer reads and address-of are
not covered by this analysis, as those paths already constant-fold
differently. `--cpu 68000` output is unaffected, since the `.w` gate requires
`supports_scaled_index`.

For struct-array members, a field displacement is folded directly into the
indexed operand's displacement (e.g. `8(a0,d1.l)`) whenever `--cpu 68020` is
selected and the offset fits the signed 8-bit brief-displacement range
(-128..127), or the target supports full-extension addressing for larger
offsets. This folding applies regardless of struct size, so real-world
structs outside the `{2, 4, 8}`-byte scaled-addressing set, such as the 10-,
11-, and 29-byte `explosions`, `Enemy`, and `bullet` structs in
`examples/games/launchers/launchers.has`, save one `add.l`-style instruction
per field access. Scale-factor addressing itself (using `*2`, `*4`, or `*8`
in the operand) remains a separate optimization that still only applies when
the struct stride is exactly `2`, `4`, or `8` bytes; larger or non-power-of-two
strides are never forced into a scaled operand, but still benefit from
displacement folding. `--cpu 68000` output is unaffected either way and
keeps the displacement as explicit `add.l` arithmetic.

Fallback lowering is target-independent: strides `16` and `32` use long shifts,
other strides through `32767` use `mulu.w`, and larger strides use full-width
shift/add multiplication rather than a truncating word multiply. These paths
preserve the existing 68000-compatible address calculation.

Assemble generated output with the matching vasm CPU flag:

```bash
python -m hasc.cli input.has --cpu 68000 -o /tmp/output-68000.s
vasmm68k_mot -m68000 -Fhunkexe -o /tmp/output-68000.o /tmp/output-68000.s

python -m hasc.cli input.has --cpu 68020 -o /tmp/output-68020.s
vasmm68k_mot -m68020 -Fhunkexe -o /tmp/output-68020.o /tmp/output-68020.s
```

#### 2D Array Access
```m68k
; Calculate: base + (row * col_count + col) * element_size
move.l row_expr,d1         ; Evaluate row
move.l d1,d2               ; Save row
move.l col_expr,d1         ; Evaluate col
; Full-width shift/add sequence computes d2 = row * col_count using d3 scratch.
move.l d2,d3
clr.l d2
add.l d1,d2                ; + col
lsl.l #2,d2                ; * 4 (element size)
lea arrayname,a0           ; Load base address
move.l (a0,d2.l),d0        ; Load element
```

The final element-size scaling is target-aware: 68000 uses an explicit long
shift or arithmetic fallback, while 68020 may use a legal scaled operand such
as `(a0,d2.l*4)`. Row multiplication remains full-width and does not use
`mulu.w`.

### Narrow element extension rules

A `move.b`/`move.w` writes only the low 8 or 16 bits of the destination, so a
byte- or word-sized element read must always be paired with an extension;
otherwise the upper bits keep whatever the previous computation left there.
`emit_narrow_element_load()` in `hasc/codegen_indexed_address.py` is the single
place that decides this, and it is used by `emit_1d_array_read()`,
`emit_2d_array_read()`, and `emit_typed_pointer_read()` (both the constant- and
variable-index branches).

| Element / pointee type | `--cpu 68000` | `--cpu 68020` |
| --- | --- | --- |
| signed 8-bit (`i8`, `byte`, `char`, `BYTE`) | `move.b` + `ext.w` + `ext.l` | `move.b` + `extb.l` |
| unsigned 8-bit (`u8`, `bool`, `UBYTE`) | `clr.l` + `move.b` | `clr.l` + `move.b` |
| signed 16-bit (`i16`, `word`, `short`, `WORD`) | `move.w` + `ext.l` | `move.w` + `ext.l` |
| unsigned 16-bit (`u16`, `UWORD`) | `clr.l` + `move.w` | `clr.l` + `move.w` |
| 32-bit and pointer types | `move.l` | `move.l` |

Zero-extension is hoisted to a `clr.l` *before* the load (6 cycles / 2 bytes)
rather than a trailing `andi.l #$FF`/`#$FFFF` (14 cycles / 6 bytes). The
`clr.l` must be emitted after the address prelude, because the prelude computes
the scaled index into the index register. When the destination register aliases
that still-live index register, hoisting is illegal and the trailing `andi.l`
form is used instead.

Signedness for global arrays is recorded by `_build_array_dimensions()` in
`hasc/codegen.py` from `ast.GlobalVarDecl.signed`, which is only set by the
opt-in typed declaration form (`grid: i8[4] = {...}`). The legacy suffix form
(`grid.b[4]`) carries no type information and is treated as unsigned, matching
the existing behavior for scalar globals. Typed pointer reads classify the
pointee type directly with `ast.is_signed()`.

Regression coverage lives in `tests/test_narrow_element_reads.py` and
`examples/tests/compiler/narrow_element_read_test.has`.

### 5. Register Preservation Fixes

#### Problem Areas Fixed:
1. **BinOp expressions**: Added `ArrayAccess` to complex expression check
2. **Array access**: Removed unnecessary d0 preservation
3. **2D arrays**: Use full-width shift/add multiplication with d3 as scratch
4. **Call expressions**: Added proper result register handling

#### Register Usage Strategy:
- `d0`: Primary result register (reg_left)
- `d1`: Secondary operand register (reg_right)
- `d2`: Temp for 2D array calculations
- `a0`: Address register for array base
- Stack: Preserve left operand in complex binary operations

### 6. Validator Updates (`hasc/validator.py`)
- Added `ArrayAccess` validation
- Validates all index expressions recursively
- Fixed for-loop counter handling to avoid false duplicate errors

## Test Files Created

### `examples/tests/compiler/array_access_test.has`
Basic array access tests:
- 1D array with variable index
- 2D array access
- Constant indices
- Array access in expressions

### `examples/tests/compiler/array_comprehensive_test.has`
Advanced tests:
- Nested array access in complex expressions
- Array access with function call results
- Array access in loops
- Register preservation with PUSH/POP

## Generated Assembly Quality

### Optimizations:
[x] No unnecessary register preservation
[x] Efficient indexed addressing modes, including legal 68020 scaled forms
[x] Full-width 2D row multiplication with an explicit d3 scratch contract
[x] Proper left-shift for scaling (faster than multiply)

### Correct register preservation:
[x] Binary operations preserve left operand when needed
[x] Array access doesn't clobber d3-d7 or a2-a6
[x] PUSH/POP properly saves/restores registers
[x] Function calls preserve caller-save registers

## Limitations & Future Work

### Current Limitations:
- Local arrays not yet supported (stack allocation needed)
- Full-extension indexed addressing is enabled under `--cpu 68020` (Phase 1 of
  `docs/CPU_68020_IMPLEMENTATION_PLAN.md`): scaled operands with displacements
  outside the -128..127 brief range, such as `1000(a0,d1.l*4)`, are emitted
  directly instead of falling back to explicit arithmetic. This is reachable
  today for dynamic array/pointer indexing with large per-element strides (see
  `examples/cpu68020_dynamic_large_index.has`). For struct-array field access,
  *scaled* addressing (`*2`, `*4`, `*8` in the operand) is still only enabled
  when the struct's total size is exactly 2, 4, or 8 bytes. However, field
  displacement folding is no longer limited to those sizes: `emit_struct_array_read()`
  and `emit_struct_array_store()` in `hasc/codegen_indexed_address.py` fold a
  field's `field_offset` into the indexed operand's displacement for any
  struct size, provided the offset fits the brief-displacement range or the
  target supports full-extension addressing. This covers real-world structs
  such as the 10-, 11-, and 29-byte `explosions`, `Enemy`, and `bullet` structs
  in `examples/games/launchers/launchers.has`, eliminating one explicit
  `add.l`-style instruction per field access on 68020. Memory-indirect forms
  remain unimplemented.
- `.w` index selection (Phase 2 of `docs/CPU_68020_IMPLEMENTATION_PLAN.md`) is
  enabled only for compile-time-constant indexes within the signed 16-bit
  range, and only at the four call sites listed above; non-constant indexes
  and the excluded call sites (typed-pointer reads, address-of) keep the `.l`
  index size.
- Other 68020 instruction substitutions are not part of this target
- 3D+ arrays not implemented
- Array bounds checking not implemented

### Future Enhancements:
- Support different element sizes (.b, .w, .l)
- Runtime bounds checking (optional)
- Pointer arithmetic for array-like access
- Array assignment: `arr[i] = value`
- Local array support with stack allocation

## Examples

### 1D Array Access:
```has
var value: int = numbers[index];
```

### 2D Array Access:
```has
var element: int = matrix[row][col];
```

### Complex Expression:
```has
result = arr1[i] + matrix[i][j] * 2 - arr2[j];
```

### In Loops:
```has
for i = 0 to 9 {
    sum = sum + arr[i];
}
```

## Testing

All tests compile successfully:
- [x] `examples/tests/compiler/array_access_test.has` -> `array_access_test.s`
- [x] `examples/tests/compiler/array_comprehensive_test.has` -> `array_comprehensive_test.s`
- [x] `examples/add.has` (regression test) -> `t.s`

Register preservation verified in generated assembly.
