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
| d0  | x0      | Left edge of region (0–319) |
| d1  | y0      | Top edge of region (0–255/511) |
| d2  | x1      | Right edge of region (must be > x0) |
| d3  | y1      | Bottom edge of region (must be > y0) |
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

### Scroll Sub-Region Left
```has
var rc: int = Scroll(50, 50, 270, 200, -1, 0, 4);
```

### Check Result
```has
if (Scroll(...) == 0) {
    // Success
} else {
    // Error: invalid region or unsupported mode
}
```

## Constraints

✅ **Works in**: Mode 0, Mode 1 (16/4 color indexed)  
❌ **Does NOT work in**: HAM6, other modes  
✅ **Uses**: Amiga Blitter (may block if busy)  
✅ **Registers**: All parameters in d0–d6, no stack  
✅ **ABI**: Standard 68000 (rts pops return address)

## Performance Notes

- **No stack overhead**: All parameters in registers (vs. 7 stack pushes)
- **Single `jsr`**: ~20 instruction bytes for parameter setup vs. 32 bytes stack-based
- **Blitter operation**: Scrolling is accelerated but may have variable latency

## Common Errors

| Error | Cause |
|-------|-------|
| Returns -1 | Invalid region (x0 ≥ x1 or y0 ≥ y1) |
| Returns -1 | Coordinates out of screen bounds |
| Returns -1 | Graphics mode is HAM6 or other unsupported mode |
| Crash/hang | Blitter in undefined state (use TakeSystem first) |

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

- [SCROLL_FUNCTION_DESIGN.md](SCROLL_FUNCTION_DESIGN.md) — Full specification
- [EXTERNAL_MODULES.md](EXTERNAL_MODULES.md) — How extern declarations work
- [TERMINOLOGY.md](TERMINOLOGY.md) — Calling conventions overview
