# Bitwise Operators

## Operators

### Binary Bitwise Operators
- `&` - Bitwise AND
- `|` - Bitwise OR (pipe character)
- `^` - Bitwise XOR (caret)

### Unary Bitwise Operator
- `~` - Bitwise NOT (tilde) - one's complement

## Operator Precedence

In the current grammar, bitwise operators bind more tightly than shifts and
comparisons, but less tightly than arithmetic. From highest to lowest, their
relative levels are: multiplicative, additive, bitwise AND (`&`), bitwise XOR
(`^`), bitwise OR (`|`), shifts (`<<`, `>>`), comparisons, logical AND
(`&&`), and logical OR (`||`). See the complete grammar-aligned table in
[Operators](OPERATORS.md#operator-precedence-highest-to-lowest).

## Assembly Implementation

All bitwise operations use 68000 long-word versions:

```asm
and.l d1,d0     ; Bitwise AND
or.l d1,d0      ; Bitwise OR
eor.l d1,d0     ; Bitwise XOR (exclusive or)
not.l d0        ; Bitwise NOT (one's complement)
```

## Examples

### Bit Masking
```has
var status: long = 0;
var ENABLE_FLAG: long = 1;

// Set a flag
status = status | ENABLE_FLAG;

// Check if flag is set
if (status & ENABLE_FLAG) {
    // flag is set
}

// Clear a flag
status = status & ~ENABLE_FLAG;
```

### Bit Extraction
```has
var byte_value: long = 255;
var lower_nibble: long = byte_value & 15;    // Extract bits 0-3
var upper_nibble: long = (byte_value >> 4) & 15;  // Extract bits 4-7
```

### Bit Toggling
```has
var flags: long = 8;  // bit 3 set
flags = flags ^ 8;    // Toggle bit 3
```

## Distinction from Address-Of

The `&` operator has two different meanings depending on context:

```has
// Unary prefix: address-of
var ptr: long* = &my_variable;

// Binary infix: bitwise AND
var result: long = value & mask;
```

The parser disambiguates based on position:
- Prefix position (after operators like `=`, `(`, etc.) → address-of
- Infix position (between values) → bitwise AND

See `examples/tests/compiler/bitwise_test.has` and `examples/bitwise_comprehensive.has` for more examples.
