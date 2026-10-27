# Scroll Function - Practical Code Examples

This document provides code examples for common scrolling scenarios. Runtime
use assumes `TakeSystem()` has established the custom-chip base in `a5`,
`SetGraphicsMode()` has succeeded, and `Scroll` is declared as external. The
test examples must be called on Amiga hardware or an emulator to exercise the
library routine; compiling them only checks HAS/assembly generation.

## Quick Reference

```has
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                   __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                   __reg(d6) pixels: int) -> int;
```

## Example 1: Basic Full-Screen Scroll Up

Scroll the entire screen upward by a fixed pixel count. This is the most common use case for game backgrounds and text scrolling.

```has
code main:
    extern func SetGraphicsMode(__reg(d0) mode: int) -> int;
    extern func ClearScreen() -> int;
    extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                       __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                       __reg(d6) pixels: int) -> int;

    proc main() -> int {
        var result: int;
        
        // Initialize lores mode (320x256x32)
        result = SetGraphicsMode(0);
        if (result != 0) {
            return -1;  // Mode not available
        }
        
        // Clear screen
        result = ClearScreen();
        
        // Scroll full screen up by 16 pixels
        result = Scroll(0, 0, 319, 255, 0, -1, 16);
        
        if (result != 0) {
            return -1;  // Scroll error
        }
        
        return 0;
    }
```

## Example 2: Scroll Direction Variants

Helper procedures for vertical and horizontal scrolling. Horizontal `Scroll`
is limited to lores and dual-playfield modes and to full-width scanlines.

```has
proc scroll_screen_up(pixels: int) -> int {
    // Scroll entire screen upward
    // vert = -1 means up, newly exposed rows appear at bottom (filled with black)
    return Scroll(0, 0, 319, 255, 0, -1, pixels);
}

proc scroll_screen_down(pixels: int) -> int {
    // Scroll entire screen downward
    // vert = 1 means down, newly exposed rows appear at top (filled with black)
    return Scroll(0, 0, 319, 255, 0, 1, pixels);
}

proc scroll_screen_left(pixels: int) -> int {
    // Horizontal pixel scroll: mode 0/3; x0=0, x1=319
    return Scroll(0, 0, 319, 255, -1, 0, pixels);
}

proc scroll_screen_right(pixels: int) -> int {
    // Horizontal pixel scroll: mode 0/3; x0=0, x1=319
    return Scroll(0, 0, 319, 255, 1, 0, pixels);
}
```

## Example 3: Scrolling a Vertical Band

Scroll a range of rows while leaving rows above and below unchanged. Vertical
`Scroll` always processes the full scanline width; `x0` and `x1` do not crop
the operation.

```has
proc scroll_rows(y_top: int, y_bottom: int, pixels: int) -> int {
    // Scroll full-width rows (e.g., 32 through 224); UI rows outside stay fixed.
    var result: int;
    
    result = Scroll(0, y_top, 319, y_bottom, 0, -1, pixels);
    
    if (result != 0) {
        return -1;  // Error
    }
    
    return 0;
}

proc scroll_menu_rows(y0: int, y1: int, pixels: int) -> int {
    // Scroll menu rows across the full screen width; this is not x-clipped.
    var result: int;
    
    result = Scroll(0, y0, 319, y1, 0, -1, pixels);
    
    if (result != 0) {
        return -1;  // Region out of bounds or invalid
    }
    
    return 0;
}
```

## Example 4: Safe Scroll with Input Validation

Validate parameters before calling `Scroll` to catch errors early.

```has
proc safe_scroll_up(pixels: int) -> int {
    // Validate input range (prevent excessive scrolling)
    if (pixels <= 0) {
        return -1;  // Pixels must be positive
    }
    
    if (pixels > 256) {
        return -1;  // Pixels too large (sanity check)
    }
    
    // Attempt scroll
    var result: int = Scroll(0, 0, 319, 255, 0, -1, pixels);
    
    if (result != 0) {
        // Scroll failed (for example, invalid bounds or HAM6 mode)
        return -1;
    }
    
    return 0;  // Success
}

proc safe_scroll_rows(y0: int, y1: int, vert: int, pixels: int) -> int {
    // Validate a vertical full-width row range before scrolling.
    
    // Check coordinates
    if (y0 < 0 || y0 >= y1) {
        return -1;  // Invalid region
    }
    
    // This helper targets lores/dual-playfield geometry.
    if (y1 > 255) {
        return -1;  // Bottom edge out of bounds
    }
    
    // Check direction values
    if (vert < -1 || vert > 1) {
        return -1;  // Invalid direction
    }
    
    // Check pixel count
    if (pixels <= 0) {
        return -1;  // Pixels must be positive
    }
    
    // All checks passed, perform scroll
    // Use full-width bounds: vertical Scroll does not crop by x.
    return Scroll(0, y0, 319, y1, 0, vert, pixels);
}
```

## Example 5: Animation Loop with Continuous Scrolling

Scroll repeatedly to create smooth animation.

```has
proc animate_scroll_loop(num_frames: int, pixels_per_frame: int) -> int {
    // Scroll the screen repeatedly over multiple frames
    // Useful for parallax effects or scrolling text
    
    var frame: int = 0;
    var result: int;
    
    while (frame < num_frames) {
        // Scroll up by pixels_per_frame
        result = Scroll(0, 0, 319, 255, 0, -1, pixels_per_frame);
        
        if (result != 0) {
            // Scroll failed
            return -1;
        }
        
        // In a real game, you would:
        // - Render new content at the bottom
        // - Wait for VBlank
        // - Swap buffers
        // - Continue to next frame
        
        frame = frame + 1;
    }
    
    return 0;  // All frames completed successfully
}

proc parallax_scroll(bg_pixels: int, fg_pixels: int) -> int {
    // Scroll background and foreground at different speeds for parallax effect
    
    // Scroll background (slow)
    var result: int = Scroll(0, 0, 319, 127, 0, -1, bg_pixels);
    if (result != 0) {
        return -1;
    }
    
    // Scroll foreground (fast)
    result = Scroll(0, 128, 319, 255, 0, -1, fg_pixels);
    if (result != 0) {
        return -1;
    }
    
    return 0;
}
```

## Example 6: Error Handling Pattern

Comprehensive error handling for production code.

```has
proc robust_scroll(x0: int, y0: int, x1: int, y1: int, 
                   hor: int, vert: int, pixels: int) -> int {
    var result: int;
    
    // Pre-flight checks
    if (pixels <= 0) {
        return -1;  // Invalid pixel count
    }
    
    if (x0 < 0 || y0 < 0 || x0 >= x1 || y0 >= y1) {
        return -1;  // Invalid region (must be x0 < x1 and y0 < y1)
    }
    
    // Attempt scroll
    result = Scroll(x0, y0, x1, y1, hor, vert, pixels);
    
    // Handle result
    if (result == 0) {
        return 0;  // Success
    } else if (result == -1) {
        // Scroll failed - possible causes include:
        // - Coordinates out of bounds for current mode
        // - Unsupported horizontal bounds/mode
        // - HAM6 mode active (unsupported)
        return -1;
    } else {
        // Unexpected return value
        return -2;
    }
}
```

## Example 7: Mode-Aware Vertical Scrolling

Adjust scroll parameters based on current graphics mode.

```has
proc scroll_full_screen_adaptive(mode: int, pixels: int) -> int {
    // Caller passes the current mode; there is no GetGraphicsMode API.
    var max_x: int;
    var result: int;
    
    if (mode == 0) {
        // Lores: 320x256x32
        max_x = 319;
    } else if (mode == 1) {
        // Hires: 640x256x16
        max_x = 639;
    } else if (mode == 3) {
        // Dual playfield: 320x256; only the active playfield is scrolled
        max_x = 319;
    } else {
        return -1;  // HAM6 or unknown mode
    }
    
    result = Scroll(0, 0, max_x, 255, 0, -1, pixels);
    return result;
}
```

## Example 8: Scrolling with Double-Buffering

Combine scrolling with double-buffered rendering.

```has
extern func SetGraphicsMode(__reg(d0) mode: int) -> int;
extern func ClearScreen() -> int;
extern func SwapScreen() -> int;
extern func UpdateCopperList() -> int;
extern func SetPixel(__reg(d0) x: int, __reg(d1) y: int, __reg(d2) color: int) -> int;
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                   __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                   __reg(d6) pixels: int) -> int;

proc render_and_scroll_loop() -> int {
    var frame: int = 0;
    var result: int;
    
    // Initialize graphics
    result = SetGraphicsMode(0);
    if (result != 0) {
        return -1;
    }
    
    ClearScreen();
    UpdateCopperList();
    SwapScreen();
    
    // Main loop
    while (frame < 100) {
        // Clear the newly exposed area (will be filled by Scroll with black)
        ClearScreen();
        
        // Scroll the screen up by 2 pixels each frame
        result = Scroll(0, 0, 319, 255, 0, -1, 2);
        if (result != 0) {
            return -1;
        }
        
        // Render new content at the bottom
        // (In a real app, draw your game sprites, tiles, etc. here)
        SetPixel(160, 254, 31);  // White pixel at bottom
        
        // Display the frame
        UpdateCopperList();
        SwapScreen();
        
        frame = frame + 1;
    }
    
    return 0;
}
```

## Example 9: Validate Scroll Bounds

Reject invalid coordinates for a lores vertical scroll. The helper does not
clip or scroll a horizontally bounded window; vertical `Scroll` always
processes full-width scanlines.

```has
proc safe_lores_vertical_scroll(y0: int, y1: int, pixels: int) -> int {
    // Validate bounds before calling Scroll; it does not reject negative y0.
    if (y0 < 0 || y0 >= y1 || y1 > 255 || pixels <= 0) {
        return -1;
    }
    
    // Vertical movement uses full-width scanlines.
    return Scroll(0, y0, 319, y1, 0, -1, pixels);
}
```

## Example 10: Game Loop Integration

A minimal game loop that combines scrolling with input and rendering.

```has
extern func SetGraphicsMode(__reg(d0) mode: int) -> int;
extern func ClearScreen() -> int;
extern func UpdateCopperList() -> int;
extern func SwapScreen() -> int;
extern func SetPixel(__reg(d0) x: int, __reg(d1) y: int, __reg(d2) color: int) -> int;
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                   __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                   __reg(d6) pixels: int) -> int;

proc game_loop() -> int {
    var running: int = 1;
    var result: int;
    var frame: int = 0;
    
    // Initialize
    result = SetGraphicsMode(0);
    if (result != 0) {
        return -1;
    }
    
    ClearScreen();
    
    // Main loop
    while (running != 0) {
        // (In a real game, check input here and set scroll directions)
        
        // Scroll background at 4 pixels per frame
        if (frame % 2 == 0) {  // Every other frame to slow down scroll
            result = Scroll(0, 0, 319, 255, 0, -1, 4);
            if (result != 0) {
                return -1;  // Scroll failed
            }
        }
        
        // Render game content
        // - Draw sprites at new positions
        // - Update HUD
        // etc.
        
        // Display and wait for VBlank
        UpdateCopperList();
        SwapScreen();
        
        frame = frame + 1;
        
        if (frame > 1000) {
            running = 0;  // Exit after 1000 frames
        }
    }
    
    return 0;
}
```

## Common Pitfalls

### ❌ Forget to Check Return Value

```has
// DON'T: Ignore errors
Scroll(0, 0, 319, 255, 0, -1, 16);  // What if this fails?
```

### ✅ Always Check Return Value

```has
// DO: Check for errors
var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);
if (result != 0) {
    return -1;  // Handle error
}
```

### ✅ Use the supported horizontal pixel-scroll path

```has
// Scroll() shifts whole pixels in mode 0 or mode 3 across a full-width row.
var result: int = Scroll(0, 0, 319, 255, -1, 0, 1);
```

For hardware fine scrolling by up to 15 pixels, use the separate
`ScrollHorizontalScreen(px)` API. It supports modes 0, 1, and 3; it changes
`BPLCON1` but does not step bitplane pointers.

Horizontal `Scroll()` is not supported in hires mode 1 and rejects partial
horizontal regions. For the exact x-boundary rules, see
[Scroll Function](SCROLL_FUNCTION.md#horizontal-pixel-scrolling-scroll).

### ✅ Use Vertical Scrolling Across Full-Width Rows

```has
// DO: Vertical scrolling is fully implemented
var result: int = Scroll(0, 0, 319, 255, 0, -1, 16);
// This works correctly
```

### ❌ Assume Filled Area Color

```has
// DON'T: Assume you can choose fill color
Scroll(0, 0, 319, 255, 0, -1, 16);
// Newly exposed rows are ALWAYS black (color 0), no option to change
```

### ✅ Work with Black Fill

```has
// DO: Accept black fill and render over it
Scroll(0, 0, 319, 255, 0, -1, 16);
// Now draw your new content at the scrolled position
SetPixel(160, 255, 31);  // Draw white pixel at new bottom row
```

## Performance Tips

1. **Scroll by row range:** Vertical `Scroll` affects full-width scanlines; use y ranges to keep rows above or below fixed.

2. **Use appropriate pixel counts:** Scrolling very small amounts (1–2 pixels) frequently is less efficient than scrolling larger amounts less often.

3. **Call during VBlank:** For smooth animation, call `Scroll` during the VBlank interval to avoid visible tearing or flicker.

4. **Minimize the row range:** Vertical work scales with the selected rows, but it does not support horizontal clipping.

5. **Avoid HAM6 mode:** HAM6 is not supported; vertical scrolling works in modes 0, 1, and 3.

## See Also

- [SCROLL_FUNCTION.md](SCROLL_FUNCTION.md) – Comprehensive user guide
- [examples/scroll_comprehensive_test.has](../examples/scroll_comprehensive_test.has) – Test suite
- [examples/scroll_function_demo.has](../examples/scroll_function_demo.has) – Additional examples
