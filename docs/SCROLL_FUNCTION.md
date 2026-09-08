# Scroll Function - User Guide

The `Scroll` function is a graphics library routine that scrolls a rectangular region of the screen by a specified number of pixels in the horizontal and/or vertical direction. It is available in [lib/graphics.s](../lib/graphics.s) and can be called directly from HAS code.

## Overview

Scrolling is a common operation in graphics applications: menus, game scrolls, text windows, and animation loops all rely on moving pixel data within a screen region and filling newly exposed areas with a background color. The `Scroll` function automates this operation with CPU-based copying for correctness and efficiency.

- **Supported modes:** Lores (320×256×32 colors), Hires (640×256×16 colors), and dual
  playfield (320×256, mode 3; scrolls only whichever playfield `SetActivePlayfield` last
  selected)
- **Vertical scrolling:** Fully implemented, using byte-aligned CPU copy
- **Horizontal scrolling:** Stubbed (returns success but performs no operation)
- **HAM6 mode:** Not supported; returns error
- **Fill color:** Newly exposed areas are always filled with black (color 0)

## Function Signature

```has
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                   __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                   __reg(d6) pixels: int) -> int;
```

All parameters are passed in data registers using the efficient register calling convention.

## Parameters

| Parameter | Register | Type | Range | Purpose |
|-----------|----------|------|-------|---------|
| `x0` | `d0` | int | 0–319 (lores/dual playfield), 0–639 (hires) | Left edge of scroll region (inclusive) |
| `y0` | `d1` | int | 0–255 | Top edge of scroll region (inclusive) |
| `x1` | `d2` | int | >x0 | Right edge of scroll region (inclusive) |
| `y1` | `d3` | int | >y0 | Bottom edge of scroll region (inclusive) |
| `hor` | `d4` | int | -1, 0, 1 | Horizontal direction: -1 = left, 0 = no-op, 1 = right |
| `vert` | `d5` | int | -1, 0, 1 | Vertical direction: -1 = up, 0 = no-op, 1 = down |
| `pixels` | `d6` | int | >0 | Number of pixels to scroll |

## Return Values

| Value | Meaning |
|-------|---------|
| `0` | Success; scroll operation completed |
| `-1` | Error; invalid parameters or unsupported graphics mode |

Errors occur when:
- Coordinates are invalid: `x0 >= x1`, `y0 >= y1`, or out-of-bounds for current graphics mode
- `pixels <= 0`
- `hor` or `vert` outside the range [-1, 0, 1]
- Current graphics mode is HAM6 (mode 2)
- Graphics mode not initialized (no screen buffer set up)

## Graphics Mode Support

### Lores Mode (Mode 0) – 320×256×32 Colors

- **Resolution:** 320 pixels wide × 256 pixels high
- **Bitplanes:** 5 (32 colors)
- **Bytes per scanline:** 40 bytes (5 bitplanes × 8 bytes each)
- **Valid coordinates:** x ∈ [0, 319], y ∈ [0, 255]

```has
var rc: int = SetGraphicsMode(0);  // Lores
var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);  // Full screen, scroll up
```

### Hires Mode (Mode 1) – 640×256×16 Colors

- **Resolution:** 640 pixels wide × 256 pixels high
- **Bitplanes:** 4 (16 colors)
- **Bytes per scanline:** 80 bytes (4 bitplanes × 20 bytes each)
- **Valid coordinates:** x ∈ [0, 639], y ∈ [0, 255]

```has
var rc: int = SetGraphicsMode(1);  // Hires
var result: int = Scroll(0, 0, 639, 255, 0, 1, 8);   // Full screen, scroll down
```

### HAM6 Mode (Mode 2) – Not Supported

HAM6 (Hold-And-Modify) mode is not supported by `Scroll`. Any attempt to scroll while in HAM6 mode returns `-1`.

### Dual Playfield Mode (Mode 3) – Active Playfield Only

- **Resolution:** 320 pixels wide × 256 pixels high (same geometry as lores)
- **Bitplanes:** 3 owned planes per playfield (6 total, split evenly between Playfield 1 and Playfield 2)
- **Bytes per scanline:** 40 bytes per owned plane, same convention as lores
- **Valid coordinates:** x ∈ [0, 319], y ∈ [0, 255]

`Scroll` scrolls only whichever playfield `SetActivePlayfield` last selected, leaving the
sibling playfield's bitplanes completely untouched.

```has
var rc: int = SetGraphicsMode(3);          // Dual playfield
call SetActivePlayfield(1);
var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);  // Scrolls Playfield 1 only
```

## Scrolling Direction Semantics

Scrolling semantics follow visual convention: a "scroll up" operation moves content upward (the top line scrolls off, new lines appear at the bottom). The direction flags in `hor` and `vert` specify the visual direction, not the data movement direction.

### Vertical Scrolling

| `vert` | Direction | Behavior |
|--------|-----------|----------|
| `-1` | Up | Content moves up; bottom rows are filled with black |
| `0` | None | No vertical scrolling |
| `1` | Down | Content moves down; top rows are filled with black |

### Horizontal Scrolling

| `hor` | Direction | Behavior |
|-------|-----------|----------|
| `-1` | Left | ⚠️ **Stubbed** — returns 0 but does nothing |
| `0` | None | No horizontal scrolling |
| `1` | Right | ⚠️ **Stubbed** — returns 0 but does nothing |

## Implementation Details

### Vertical Scrolling Algorithm

When scrolling vertically, `Scroll` uses the following algorithm:

1. **Validate region bounds** and that `pixels > 0`
2. **Calculate stride** = bytes per scanline × number of bitplanes
3. **Check if scroll amount ≥ region height:**
   - If yes, clear the entire region to black (color 0)
   - If no, continue to partial scroll
4. **Copy visible lines:**
   - **Scroll up (vert = -1):** Copy lines downward (forward) from the source region to avoid overwriting. The source is lines at `y0 + pixels` through `y1`; the destination is lines at `y0` through `y1 - pixels`. This forward copy prevents data corruption.
   - **Scroll down (vert = 1):** Copy lines upward (backward) from the source region. The source is lines at `y0` through `y1 - pixels`; the destination is lines at `y0 + pixels` through `y1`. Backward copy prevents overwriting before reading.
5. **Fill newly exposed area:**
   - **Scroll up:** Fill rows `y1 - pixels + 1` through `y1` with black
   - **Scroll down:** Fill rows `y0` through `y0 + pixels - 1` with black

### Memory Layout

For each scanline at y, the bitplane data occupies `bytes_per_row` bytes. With multiple bitplanes, the total stride is `bytes_per_row × plane_count`. For example, in lores mode:
- Bitplane 0 scanline y: bytes `y * 40 + 0..39`
- Bitplane 1 scanline y: bytes `y * 40 + 40..79`
- ...
- Bitplane 4 scanline y: bytes `y * 40 + 160..199`

The `Scroll` function copies all bitplanes as a single contiguous block per scanline using long-word (4-byte) moves for efficiency.

### Performance Characteristics

- **Vertical scrolling:** CPU-based, byte-aligned; speed depends on region size and bitplane depth
- **Horizontal scrolling:** Currently stubbed; a future version will use the Blitter for word-aligned scrolls
- **Cache locality:** Forward/backward copy order ensures sequential memory access
- **Interrupt safety:** Scrolling should be performed during VBlank or with interrupts disabled to avoid visible tearing

## Limitations and Known Issues

### Horizontal Scrolling Not Implemented

Horizontal scrolling (`hor ≠ 0`) currently returns success (0) but performs **no operation**. This is a placeholder for future Blitter-accelerated implementation. Do not rely on horizontal scrolling until it is fully implemented.

```has
// This call returns 0 but does NOT scroll horizontally:
var result: int = Scroll(0, 0, 319, 255, -1, 0, 16);  // ⚠️ Does nothing!
```

### Fill Color Fixed to Black

Newly exposed areas are always filled with color 0 (black) regardless of the graphics palette. There is no option to fill with a different color or pattern.

### Y-Coordinate Validation Required

The function validates that `y0` and `y1` are within the screen bounds (0–255), but it does **not** clamp or auto-adjust invalid coordinates. If your region extends beyond the screen, the function will return `-1`. You must ensure your coordinates are valid before calling `Scroll`.

### No Fine-Scroll Support

The pixel count is always an integer. There is no support for sub-pixel scrolling or fractional pixel offsets.

### No Clipping to Sub-Regions

The `Scroll` function assumes the region fits within a single contiguous screen buffer. If you need to scroll a region that spans multiple logical screens or requires clipping to a complex shape, you must implement that logic in HAS.

## Usage Patterns

### Basic Full-Screen Scroll

```has
// Scroll entire screen up by 16 pixels
var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);
if (result != 0) {
    // Error: graphics mode not initialized or HAM6
    return -1;
}
```

### Scroll a Sub-Region

```has
// Scroll a window from (100, 50) to (250, 200) down by 8 pixels
var result: int = Scroll(100, 50, 250, 200, 0, 1, 8);
```

### Conditional Scrolling Based on Mode

```has
proc mode_aware_scroll(pixels: int) -> int {
    var mode: int = GetGraphicsMode();  // Hypothetical function
    var max_x: int;
    
    if (mode == 0) {
        max_x = 319;  // Lores
    } else {
        max_x = 639;  // Hires
    }
    
    return Scroll(0, 0, max_x, 255, 0, -1, pixels);
}
```

### Animation Loop with Repeated Scrolls

```has
proc scroll_animation(num_frames: int, pixels_per_frame: int) -> int {
    var frame: int = 0;
    var result: int;
    
    while (frame < num_frames) {
        result = Scroll(0, 0, 319, 255, 0, -1, pixels_per_frame);
        if (result != 0) {
            return -1;  // Scroll failed
        }
        frame = frame + 1;
    }
    
    return 0;
}
```

### Error Handling Pattern

```has
proc safe_scroll_up(pixels: int) -> int {
    // Validate input
    if (pixels <= 0 || pixels > 256) {
        return -1;  // Invalid pixel count
    }
    
    // Attempt scroll
    var result: int = Scroll(0, 0, 319, 255, 0, -1, pixels);
    
    if (result != 0) {
        // Scroll failed (mode may not be initialized)
        return -1;
    }
    
    return 0;
}
```

## Testing and Verification

The [examples/scroll_comprehensive_test.has](../examples/scroll_comprehensive_test.has) file contains seven test cases that validate:

1. **Vertical scroll up** – Full-screen scroll up by 10 pixels
2. **Vertical scroll down** – Full-screen scroll down by 16 pixels
3. **Sub-region scroll** – Scroll a window region up by 5 pixels
4. **Large scroll** – Scroll that exceeds region height (full clear)
5. **Invalid coordinates** – Error case where x0 ≥ x1
6. **Zero pixels** – Error case where pixels = 0
7. **No direction** – Case where both hor and vert are 0

To compile and test:

```bash
python3 -m hasc.cli examples/scroll_comprehensive_test.has -o /tmp/scroll_test.s
vasmm68k_mot -Fhunkexe -o /tmp/scroll_test.o /tmp/scroll_test.s
```

## Integration with Other Graphics Functions

The `Scroll` function operates on the current screen buffer (set by `SetGraphicsMode` and `UpdateCopperList`). It is compatible with other graphics functions such as `SetPixel`, `LINE`, `RECTANGLE`, and `CIRCLE`. Use `ClearScreen` to initialize a blank canvas, then `Scroll` to perform scrolling operations.

```has
extern func SetGraphicsMode(mode: int) -> int;
extern func ClearScreen() -> int;
extern func SetPixel(x: int, y: int, color: int) -> int;
extern func Scroll(x0: int, y0: int, x1: int, y1: int, hor: int, vert: int, pixels: int) -> int;
extern func UpdateCopperList() -> int;
extern func SwapScreen() -> int;

proc main() -> int {
    // Initialize lores mode
    SetGraphicsMode(0);
    ClearScreen();
    
    // Draw a test pattern
    SetPixel(160, 128, 31);  // White pixel at center
    
    // Scroll up by 32 pixels
    Scroll(0, 0, 319, 255, 0, -1, 32);
    
    // Update display
    UpdateCopperList();
    SwapScreen();
    
    return 0;
}
```

## ScrollHorizontalScreen (Hardware Fine Scroll)

`ScrollHorizontalScreen` is a separate, lightweight function that sets the OCS/ECS hardware
fine-scroll register (`BPLCON1`) directly, instead of moving pixel data with the CPU/Blitter like
`Scroll` does. It targets the *active playfield* (whichever `SetActivePlayfield` last selected, in
mode 3) and only covers the sub-16-pixel scroll phase.

```has
extern func ScrollHorizontalScreen(px: int) -> int;
```

- **px**: signed pixel offset, `-15..15`. `px >= 0` scrolls right by `px` pixels; `px < 0` scrolls
  left by `-px` pixels. Values outside this range return `-1` without writing any register.
- **Supported modes:** 0 (lores), 1 (hires), and 3 (dual playfield, active playfield only). HAM6
  (mode 2) is rejected, same as `Scroll`.
- **Dual playfield (mode 3):** only the active playfield's `BPLCON1` nibble is updated; the
  sibling playfield's fine-scroll value is preserved untouched.
- **Scope:** this only sets the hardware delay - it does **not** move bitplane pointers or touch
  `BPL1MOD`/`BPL2MOD`. Continuous smooth scrolling beyond one 16-pixel cell still requires the
  caller to step its own bitplane pointers, exactly like the classic OCS scrolling technique.
- Returns `0` on success, `-1` on error (`px` out of range or HAM6 mode).

```has
call SetGraphicsMode(3);
call SetActivePlayfield(1);
call ScrollHorizontalScreen(5);    // Playfield 1 fine-scrolled right by 5px
call SetActivePlayfield(2);
call ScrollHorizontalScreen(-3);   // Playfield 2 independently scrolled left by 3px
```

See [examples/scroll_horizontal_screen_test.has](../examples/scroll_horizontal_screen_test.has) for
a compile-time test covering single- and dual-playfield modes plus the range/HAM6 error cases.

## Future Enhancements

The `Scroll` function is designed to support future expansion:

- **Blitter acceleration** for horizontal scrolling
- **Configurable fill color** for newly exposed areas
- **Sub-pixel scrolling** for smoother animation of `Scroll`'s CPU/Blitter copies (hardware
  sub-16-pixel scrolling is already available separately via `ScrollHorizontalScreen` above)
- **Clipping and masking** for complex scroll regions

Until these features are implemented, the function provides stable, correct vertical scrolling for games, animations, and UI applications on the Amiga platform.

## See Also

- [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) – Overview of all graphics functions
- [SCROLL_FUNCTION_DESIGN.md](SCROLL_FUNCTION_DESIGN.md) – Technical design and implementation details
- [examples/scroll_comprehensive_test.has](../examples/scroll_comprehensive_test.has) – Comprehensive test suite
- [examples/scroll_function_demo.has](../examples/scroll_function_demo.has) – Usage examples and helper functions
- [examples/scroll_horizontal_screen_test.has](../examples/scroll_horizontal_screen_test.has) – `ScrollHorizontalScreen` compile-time test
