# Scroll Function - User Guide

The `Scroll` function in [lib/graphics.s](../lib/graphics.s) moves screen
contents by whole pixels in the horizontal and/or vertical direction.

## Overview

`Scroll` uses CPU copies for vertical movement and CPU word shifts for
horizontal movement; it does not use the blitter. Vertical scrolling processes
full-width scanlines for the selected y range; `x0` and `x1` do not crop the
vertical operation.

- **Vertical scrolling:** Supported in modes 0 (lores), 1 (hires), and 3
  (dual playfield; only the active playfield is moved)
- **Horizontal pixel scrolling:** Supported in modes 0 and 3 only, with the
  full-width edge constraints listed below
- **Horizontal fine scrolling:** Use the separate
  `ScrollHorizontalScreen()` API for OCS/ECS `BPLCON1` offsets in modes 0, 1,
  and 3
- **HAM6 mode:** Not supported; returns error
- **Fill color:** Newly exposed areas are always filled with black (color 0)
- **Screen setup:** In the bare-metal graphics-library workflow, call
  `TakeSystem()` before `SetGraphicsMode()` so the custom-chip base in `a5` is
  initialized. `Scroll` does not check that the current screen pointer is
  non-null; call `SetGraphicsMode()` successfully before using it.

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
| `x0` | `d0` | int | 0–319 (lores/dual playfield), 0–639 (hires) | Left bound; horizontal scrolling has additional edge rules |
| `y0` | `d1` | int | 0–255 | Top edge of scroll region (inclusive) |
| `x1` | `d2` | int | >x0, at most mode maximum | Right bound; horizontal scrolling has additional edge rules |
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
- `x0 >= x1` or `y0 >= y1`
- `x1` or `y1` exceeds the current mode's maximum coordinates
- `pixels <= 0`
- `hor` or `vert` outside the range [-1, 0, 1]
- Current graphics mode is HAM6 (mode 2)
- A horizontal scroll uses an unsupported mode or x bounds (see below)

**Caller validation is required:** the implementation does not reject negative
`x0` or `y0`. In particular, a negative `y0` can make the vertical operation
address memory before the screen buffer. Ensure all coordinates are
non-negative and within the selected mode's bounds, and initialize the custom
chip base and screen successfully before calling.

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

`Scroll` processes only whichever playfield `SetActivePlayfield` last
selected, leaving the sibling playfield's bitplanes untouched. As in other
modes, vertical movement uses full-width scanlines; `x0` and `x1` do not limit
the vertical operation.

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

### Horizontal Pixel Scrolling (`Scroll`)

| `hor` | Direction | Behavior |
|-------|-----------|----------|
| `-1` | Left | CPU-shifts each selected scanline left |
| `0` | None | No horizontal scrolling |
| `1` | Right | CPU-shifts each selected scanline right |

Horizontal `Scroll` is supported only in mode 0 (lores) and mode 3 (dual
playfield), and requires `x1 = 319`. For a right scroll, `x0` must be `0`; for
a left scroll, `x0` may be `0` or `1` (use `1` to preserve the leftmost
column). Other horizontal regions, and horizontal `Scroll` in mode 1 (hires),
return `-1`. The selected y rows are shifted across the full width; partial
horizontal regions are not supported. In mode 3 only the active playfield is
moved.

For vertical-only movement (`hor = 0`), `x0` and `x1` are validated against
ordering and the right edge, but the implementation copies and fills complete
scanlines. They do not define a horizontal sub-region. When both directions
are requested, vertical movement still affects complete scanlines before the
horizontal shift is applied.

## Implementation Details

### Vertical Scrolling Algorithm

When scrolling vertically, `Scroll` uses the following algorithm:

1. **Validate region bounds** and that `pixels > 0`
2. **Calculate stride** = bytes per scanline × number of bitplanes
3. **Check if scroll amount ≥ region height:**
   - If yes, clear the entire region to black (color 0)
   - If no, continue to partial scroll
4. **Copy visible full-width scanlines:**
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

- Both vertical copies and horizontal pixel shifts are CPU-based; cost depends
  on the region size, bitplane count, and pixel distance.
- Forward/backward copy order avoids overwriting source data during vertical
  movement.
- Perform visible-screen updates during VBlank or with an appropriate display
  synchronization strategy to avoid tearing.

## Limitations and Known Issues

### Fill Color Fixed to Black

Newly exposed areas are always filled with color 0 (black) regardless of the graphics palette. There is no option to fill with a different color or pattern.

### Coordinate Validation Required

The function validates that region coordinates are within the current mode's
screen bounds; it does not clamp invalid coordinates. Invalid regions return
`-1`.

### No Fine-Scroll Support

The pixel count is always an integer. There is no support for sub-pixel scrolling or fractional pixel offsets.

### Vertical Scroll Is Full-Width

Vertical `Scroll` ignores `x0` and `x1` when copying or filling scanlines, so
it cannot scroll a horizontally clipped window. Horizontal pixel movement
also does not support partial-width regions. Use a separate implementation if
you need clipped or irregular shapes.

## Usage Patterns

### Basic Full-Screen Scroll

```has
// Scroll entire screen up by 16 pixels
var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);
if (result != 0) {
    // Error: invalid arguments, unsupported mode, or horizontal bounds
    return -1;
}
```

### Scroll a Sub-Region

```has
// Scroll rows 50 through 200 down by 8 pixels (full width, not an x-clipped window)
var result: int = Scroll(0, 50, 319, 200, 0, 1, 8);
```

### Conditional Scrolling Based on Mode

```has
proc mode_aware_vertical_scroll(mode: int, pixels: int) -> int {
    // Pass the mode selected by the caller; no GetGraphicsMode API is provided.
    var max_x: int;
    
    if (mode == 0) {
        max_x = 319;  // Lores
    } else if (mode == 1) {
        max_x = 639;  // Hires
    } else if (mode == 3) {
        max_x = 319;  // Dual playfield
    } else {
        return -1;    // HAM6 and unknown modes are unsupported
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
    
    // Attempt scroll; SetGraphicsMode must have succeeded first.
    var result: int = Scroll(0, 0, 319, 255, 0, -1, pixels);
    
    if (result != 0) {
        // Scroll failed (for example, invalid bounds or HAM6 mode)
        return -1;
    }
    
    return 0;
}
```

## Testing and Verification

The [examples/scroll_comprehensive_test.has](../examples/scroll_comprehensive_test.has)
file defines seven test procedures and a `run_all_tests` routine covering:

1. **Vertical scroll up** – Full-screen scroll up by 10 pixels
2. **Vertical scroll down** – Full-screen scroll down by 16 pixels
3. **Narrow x arguments with vertical scroll** – The routine currently still
   processes full-width scanlines; this call does not demonstrate x clipping
4. **Large scroll** – Scroll that exceeds region height (full clear)
5. **Invalid coordinates** – Error case where x0 ≥ x1
6. **Zero pixels** – Error case where pixels = 0
7. **No direction** – Case where both hor and vert are 0

The source does not call `run_all_tests` automatically. The following
commands only compile and assemble the test program; execute a call to
`run_all_tests` on an Amiga or emulator to check the routine's return values.
The sample's third case passes narrow x bounds but vertical `Scroll` still
affects full-width scanlines.

To compile and assemble:

```bash
python3 -m hasc.cli examples/scroll_comprehensive_test.has -o /tmp/scroll_test.s
vasmm68k_mot -Fhunkexe -o /tmp/scroll_test.o /tmp/scroll_test.s
```

## Integration with Other Graphics Functions

The `Scroll` function operates on the current screen buffer selected by a
successful `SetGraphicsMode` call. In the bare-metal graphics-library
workflow, first establish the custom-chip base with `TakeSystem()`. Initialize
and synchronize the display as needed for your application. It is compatible
with other graphics functions such as `SetPixel`, `LINE`, `RECTANGLE`, and
`CIRCLE`.

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

`ScrollHorizontalScreen` is a separate function that writes the OCS/ECS
fine-scroll register (`BPLCON1`) instead of moving pixel data like `Scroll`.
It targets the *active playfield* (whichever `SetActivePlayfield` last
selected, in mode 3) and only sets the sub-16-pixel phase; it does not move
bitplane pointers.

```has
extern func ScrollHorizontalScreen(px: int) -> int;
```

- **px**: signed input in `-15..15`. The implementation writes `abs(px)` to
  the hardware delay nibble, so `px` and `-px` produce the same register
  value. Values outside this range return `-1` without writing the register.
- **Setup:** the routine writes `BPLCON1(a5)` directly. Ensure the library's
  custom-chip base is valid in `a5` (normally established by `TakeSystem()`)
  before calling it.
- **Supported modes:** 0 (lores), 1 (hires), and 3 (dual playfield, active playfield only). HAM6
  (mode 2) is rejected, same as `Scroll`.
- **Dual playfield (mode 3):** only the active playfield's `BPLCON1` nibble is updated; the
  sibling playfield's fine-scroll value is preserved untouched.
- **Scope:** this only sets the hardware delay - it does **not** move bitplane pointers or touch
  `BPL1MOD`/`BPL2MOD`. Continuous smooth scrolling beyond one 16-pixel cell still requires the
  caller to step its own bitplane pointers, exactly like the classic OCS scrolling technique.
- **Direction caveat:** the current implementation maps both signs to the
  same delay value. Source comments and example comments describe opposite
  visual directions for positive and negative inputs, but that distinction is
  not encoded by the register value. The intended direction convention needs
  clarification; until then, treat `px` as selecting a delay magnitude only.
- Returns `0` on success, `-1` on error (`px` out of range or HAM6 mode).

```has
call SetGraphicsMode(3);
call SetActivePlayfield(1);
call ScrollHorizontalScreen(5);    // Set Playfield 1 delay nibble to 5
call SetActivePlayfield(2);
call ScrollHorizontalScreen(-3);   // Set Playfield 2 delay nibble to 3
```

See [examples/scroll_horizontal_screen_test.has](../examples/scroll_horizontal_screen_test.has) for
a test program covering single- and dual-playfield modes plus the range/HAM6
error cases. Compiling it does not execute those calls or verify visual
direction on hardware.

## See Also

- [GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md) – Overview of all graphics functions
- [examples/scroll_comprehensive_test.has](../examples/scroll_comprehensive_test.has) – Comprehensive test suite
- [examples/scroll_function_demo.has](../examples/scroll_function_demo.has) – Usage examples and helper functions
- [examples/scroll_horizontal_screen_test.has](../examples/scroll_horizontal_screen_test.has) – `ScrollHorizontalScreen` compile-time test
