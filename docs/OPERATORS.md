# Operators Implemented

## Arithmetic Operators
- `+` - Addition
- `-` - Subtraction  
- `*` - Multiplication (signed 16-bit muls.w)
- `/` - Division (signed 16-bit divs.w)
- `%` - Modulo (via divs.w, remainder in upper word)

### 68000 Arithmetic Safety Notes

- On `--cpu 68000` (default), `*`, `/`, `%` lower to 68000 word arithmetic
  (`muls.w` / `divs.w`).
- Constant operands used in these paths must fit signed 16-bit range: `-32768..32767`.
- Division/modulo by constant zero is a compile-time error.
- `#pragma strict16arith(on)` enables stricter checks for dynamic (non-constant) operands:
	- operands must be provably safe signed 16-bit values based on declared types.
- `#pragma strict16arith(off)` (default) keeps permissive behavior for dynamic operands.
- **This signed 16-bit restriction is 68000-specific and is lifted under
  `--cpu 68020`**: `*`, `/`, `%` on `int`/`long` instead emit native
  `muls.l`/`divsl.l`, supporting full 32-bit operands with no compile-time
  range restriction (gated on `TargetSpec.supports_32bit_muldiv`). Division/
  modulo by constant zero remains a compile-time error on both targets.

## Comparison Operators (all signed)
- `==` - Equal (returns 1 or 0)
- `!=` - Not equal
- `<` - Less than
- `<=` - Less than or equal
- `>` - Greater than
- `>=` - Greater than or equal

Comparison results are:
- 1 (true) if condition holds
- 0 (false) if condition doesn't hold

## Logical Operators
- `&&` - Logical AND (both operands must be non-zero)
- `||` - Logical OR (at least one operand must be non-zero)
- `!` - Logical NOT (unary prefix; zero becomes `1`, nonzero becomes `0`)

Logical results are:
- 1 (true) if condition holds
- 0 (false) if condition doesn't hold

Logical `!` is distinct from bitwise `~`: use `!value` when testing whether
`value` is zero, and `~value` when complementing every bit.

## Unary Operators
- `-` - Negation (prefix)
- `!` - Logical NOT (prefix)
- `&` - Address-of
- `*` - Dereference

## Operator Precedence (highest to lowest)

1. Unary: `!` `-` `&` `*`
2. Multiplicative: `*` `/` `%`
3. Additive: `+` `-`
4. Comparison: `<` `<=` `>` `>=`
5. Equality: `==` `!=`
6. Logical AND: `&&`
7. Logical OR: `||`

## Assembly Implementation

### Comparison Operators
Use 68000 `cmp` instruction with set conditional byte:
```asm
cmp.l d1,d0
seq d0      ; set d0 to 0xFF if equal, 0 otherwise
andi.l #$FF,d0
neg.b d0    ; convert 0xFF to 0x01, 0 stays 0
```

### Logical Operators
Use conditional branches for short-circuit evaluation:
```asm
; a && b
tst.l d0
beq.s .false
tst.l d1
beq.s .false
move.l #1,d0
bra.s .done
.false:
move.l #0,d0
.done:
```

### Modulo
Use 68000 `divs.w` and swap to get remainder:
```asm
divs.w d1,d0
swap d0      ; remainder is now in lower word
ext.l d0     ; sign-extend
```

### Division Semantics

Signed division is emitted as `divs.w` even for power-of-two divisors.
This avoids incorrect negative rounding behavior that would result from substituting arithmetic shifts.

## Examples

See `examples/tests/compiler/operators_test.has` for comprehensive operator examples.
