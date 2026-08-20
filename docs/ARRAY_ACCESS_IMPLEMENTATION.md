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

For struct-array members, a field displacement is folded into a scaled operand
only when the stride is `2`, `4`, or `8` and the displacement fits the signed
8-bit indexed displacement supported by the generated form. Otherwise the
compiler keeps the displacement as explicit arithmetic. Non-power-of-two
strides are never forced into a scaled operand.

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
  scaled addressing is only enabled when the struct's total size is exactly 2,
  4, or 8 bytes, so no real struct layout currently exceeds the brief-range
  displacement; the out-of-range struct-field path is exercised only by direct
  unit tests of the lowering helper. Memory-indirect forms remain unimplemented.
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
