% Scroll Function Quick Reference

# Scroll Function - Quick Reference Card

## Declaration

```has
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                   __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                   __reg(d6) pixels: int) -> int;
```

## Parameters (All in Registers)

| Reg | Param   | Meaning |
|-----|---------|---------|
| d0  | x0      | Left bound (0–319 lores/dual; 0–639 hires; vertical scroll ignores x clipping) |
| d1  | y0      | Top edge (0–255) |
| d2  | x1      | Right bound (> x0; max 319 lores/dual, 639 hires; vertical scroll ignores x clipping) |
| d3  | y1      | Bottom edge (must be > y0; max 255) |
| d4  | hor     | Horizontal: -1 (left), 0 (none), 1 (right) |
| d5  | vert    | Vertical: -1 (up), 0 (none), 1 (down) |
| d6  | pixels  | Scroll distance in pixels |

## Return Value

- **d0 = 0**: Success
- **d0 = -1**: Error (invalid region, unsupported mode, etc.)

## Quick Examples

### Scroll Full Screen Up
```has
var rc: int = Scroll(0, 0, 319, 255, 0, -1, 16);
```

### Scroll Full Screen Right
```has
var rc: int = Scroll(0, 0, 319, 255, 1, 0, 8);
```

### Scroll Rows Up
```has
var rc: int = Scroll(0, 50, 319, 200, 0, -1, 4);
```

Vertical movement processes full-width scanlines; `x0`/`x1` do not crop it.
Horizontal pixel movement is full width only: mode 0 or 3, `x1=319`, and
`x0=0` for right or `x0=0`/`1` for left.

### Check Result
```has
if (Scroll(...) == 0) {
    // Success
} else {
    // Error: invalid region or unsupported mode
}
```

## Constraints

✅ **Vertical scroll**: Modes 0, 1, and 3 (active playfield only in mode 3)

✅ **Horizontal pixel scroll**: Modes 0 and 3 only; `x1=319`, `x0=0` for
right, and `x0=0` or `1` for left

❌ **Does NOT work in**: Mode 2 (HAM6); horizontal pixel scroll also rejects
mode 1

✅ **Implementation**: CPU copy/shift; no blitter dependency

✅ **Parameters**: Declared in d0–d6 for the external routine

The routine validates `x0 < x1`, `y0 < y1`, and the upper bounds, but does
not reject negative `x0`/`y0`. A negative `y0` can address memory before the
screen buffer. Validate nonnegative, in-range coordinates yourself. In
bare-metal use, call `TakeSystem()` to establish the custom-chip base in `a5`,
then call `SetGraphicsMode()` successfully before using the graphics routines.
`Scroll` does not check for a null screen pointer.

## Performance Notes

- Register parameters avoid a stack-pushed argument list, but the operation
  itself is CPU-bound and its cost scales with region size and pixel distance.

## ScrollHorizontalScreen (Hardware Fine Scroll)

```has
extern func ScrollHorizontalScreen(px: int) -> int;
```

| Param | Type | Range | Meaning |
|-------|------|-------|---------|
| `px`  | int  | -15..15 | Input magnitude for the fine-scroll delay |

- Sets `BPLCON1` directly (OCS/ECS hardware register); does not move bitplane pointers.
- Writes `abs(px)` to the delay nibble, so `px` and `-px` produce the same value.
- Modes 0, 1, 3 (dual playfield: active playfield only, via `SetActivePlayfield`). HAM6 rejected.
- **d0 = 0**: Success. **d0 = -1**: `px` out of range, or HAM6 mode.

```has
call ScrollHorizontalScreen(5);   // set active playfield's delay nibble to 5
call ScrollHorizontalScreen(-5);  // same delay value: 5
```

## Common Errors

| Error | Cause |
|-------|-------|
| Returns -1 | Invalid region (x0 ≥ x1 or y0 ≥ y1) |
| Returns -1 | Coordinates out of screen bounds |
| Returns -1 | Graphics mode is HAM6 (mode 2) |
| Returns -1 | Horizontal `Scroll` used in hires or with unsupported x bounds |

## Usage Pattern

```has
code main:
    extern func Scroll(...) -> int;
    
    proc main() -> int {
        var result: int;
        result = Scroll(x0, y0, x1, y1, hor, vert, pixels);
        if (result == 0) {
            return 0;  // OK
        } else {
            return -1; // ERROR
        }
    }
```

## Related Documentation

- [SCROLL_FUNCTION.md](SCROLL_FUNCTION.md) — Full user guide and current behavior
- [EXTERNAL_MODULES.md](EXTERNAL_MODULES.md) — How extern declarations work
- [TERMINOLOGY.md](TERMINOLOGY.md) — Calling conventions overview

**Direction caveat:** the source comments and example comments describe
positive and negative inputs as opposite visual directions, but the
implementation maps both signs to the same `BPLCON1` value. The intended
direction convention needs clarification; see the full [Scroll Function
guide](SCROLL_FUNCTION.md#scrollhorizontalscreen-hardware-fine-scroll).
