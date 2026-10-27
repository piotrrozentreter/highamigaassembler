# Bit Shift Operators

Bit shift operators have been implemented in the HAS compiler for efficient bit manipulation operations.

## Operators

- `<<` - Logical left shift (multiply by powers of 2)
- `>>` - Arithmetic right shift (divide by powers of 2, sign-extends)

## Syntax

```has
result = value << shift_amount;    // Left shift
result = value >> shift_amount;    // Right shift
```

## Generated Assembly

- `<<` generates `lsl.l` (Logical Shift Left, long)
- `>>` generates `asr.l` (Arithmetic Shift Right, long)

Both instructions are 68000-compatible.

## Features

### Constant Folding
Shift expressions with constant operands are evaluated at compile time:

```has
result = 8 << 2;    // Compiled to move.l #32,d0
```

### Variable Shifts
Shift amounts can be stored in variables or computed at runtime:

```has
shift_amount = 3;
result = value << shift_amount;   // Runtime shift
```

### Complex Expressions
Shifts can be used in complex expressions with proper operator precedence:

```has
result = (x << 2) + (y >> 1);     // Parentheses for clarity
offset = base + (index << 2);      // Array indexing by long size
```

## Common Use Cases

Shifts are useful for bit-field manipulation, masks, and explicit scaling where
the desired semantics are a bit shift. The compiler also strength-reduces
multiplication by selected powers of two. Do not replace signed division with
an arithmetic right shift without checking negative-value rounding: the two
operations are not generally equivalent.

### Bit Manipulation
```has
// Set bit at position
flags = flags | (1 << position);

// Test bit at position
is_set = (flags >> position) & 1;

// Extract bits
nibble = (value >> 4) & 0x0F;
```

### Array Indexing
```has
// For array of longs (4 bytes each)
address = base + (index << 2);    // index * 4

// For array of words (2 bytes each)
address = base + (index << 1);    // index * 2

// For array of bytes (1 byte each)
address = base + index;           // no shift needed
```

### Color Packing
```has
// RGB565: RRRRR GGG GGGB BBBB
rgb565 = (r << 11) | (g << 5) | b;

// RGB888: RRRRRRRR GGGGGGGG BBBBBBBB
rgb888 = (r << 16) | (g << 8) | b;
```

## Example Code

See [examples/shift_operators_demo.has](../examples/shift_operators_demo.has) for comprehensive examples including:
- Multiply/divide by shifts
- Bit extraction and manipulation
- Array indexing optimization
- Color channel shifting
- Variable shift amounts

## Tests

Validation is example-driven in this repository. Use:
- [examples/shift_operators_demo.has](../examples/shift_operators_demo.has) for shift behavior coverage
- [examples/bitwise_comprehensive.has](../examples/bitwise_comprehensive.has) for combined bitwise+shift scenarios

Compile checks:
```bash
python -m hasc.cli examples/shift_operators_demo.has -o /tmp/shift_operators_demo.s
python -m hasc.cli examples/bitwise_comprehensive.has -o /tmp/bitwise_comprehensive.s
```

## Operator Precedence

Shifts bind less tightly than bitwise operators and more tightly than
comparisons in the current grammar. See the complete table in
[Operators](OPERATORS.md#operator-precedence-highest-to-lowest).

Use parentheses for clarity when mixing operators:
```has
result = (a << 2) + (b >> 1);    // Clear intent
```

## Semantics and Limits

- The compiler does not range-check a runtime shift count. Use a value in the
  Motorola 68k long-shift count range (0–63) when that is the intended result.
- Right shift is arithmetic (sign-extending), not logical.
- For unsigned right shift, use bitwise AND after shift: `(value >> 1) & 0x7FFFFFFF`
