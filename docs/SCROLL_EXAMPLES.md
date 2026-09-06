# Scroll Function - Practical Code Examples

This document provides ready-to-use code examples for common scrolling scenarios. All examples assume a graphics mode has been initialized with `SetGraphicsMode()` and the `Scroll` function is declared as external.

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

Helper procedures for the four directional variants.

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
    // Scroll entire screen left (STUBBED - currently does nothing)
    // WARNING: This currently returns 0 but does NOT perform scrolling
    return Scroll(0, 0, 319, 255, -1, 0, pixels);
}

proc scroll_screen_right(pixels: int) -> int {
    // Scroll entire screen right (STUBBED - currently does nothing)
    // WARNING: This currently returns 0 but does NOT perform scrolling
    return Scroll(0, 0, 319, 255, 1, 0, pixels);
}
```

## Example 3: Scrolling a Sub-Region (Window)

Scroll only part of the screen, leaving the rest unchanged.

```has
proc scroll_game_window(window_y_top: int, window_y_bottom: int, pixels: int) -> int {
    // Scroll only the game window (e.g., rows 32 to 224)
    // The UI remains fixed at the top and bottom
    var result: int;
    
    result = Scroll(0, window_y_top, 319, window_y_bottom, 0, -1, pixels);
    
    if (result != 0) {
        return -1;  // Error
    }
    
    return 0;
}

proc scroll_menu_region(x0: int, y0: int, x1: int, y1: int, pixels: int) -> int {
    // Scroll a specific rectangular menu region
    // Example: scroll items in a list box
    var result: int;
    
    result = Scroll(x0, y0, x1, y1, 0, -1, pixels);
    
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
        // Scroll failed (graphics mode not initialized, or HAM6)
        return -1;
    }
    
    return 0;  // Success
}

proc safe_scroll_region(x0: int, y0: int, x1: int, y1: int, 
                        hor: int, vert: int, pixels: int) -> int {
    // Validate all parameters before scrolling
    
    // Check coordinates
    if (x0 >= x1 || y0 >= y1) {
        return -1;  // Invalid region
    }
    
    // Check bounds for lores mode (adjust for hires if needed)
    if (x1 > 319 || y1 > 255) {
        return -1;  // Coordinates out of bounds
    }
    
    // Check direction values
    if ((hor < -1 || hor > 1) || (vert < -1 || vert > 1)) {
        return -1;  // Invalid direction
    }
    
    // Check pixel count
    if (pixels <= 0) {
        return -1;  // Pixels must be positive
    }
    
    // All checks passed, perform scroll
    return Scroll(x0, y0, x1, y1, hor, vert, pixels);
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
    
    if (x0 >= x1 || y0 >= y1) {
        return -1;  // Invalid region (must be x0 < x1 and y0 < y1)
    }
    
    // Attempt scroll
    result = Scroll(x0, y0, x1, y1, hor, vert, pixels);
    
    // Handle result
    if (result == 0) {
        return 0;  // Success
    } else if (result == -1) {
        // Scroll failed - possible causes:
        // - Graphics mode not initialized
        // - Coordinates out of bounds for current mode
        // - HAM6 mode active (unsupported)
        return -1;
    } else {
        // Unexpected return value
        return -2;
    }
}
```

## Example 7: Mode-Aware Scrolling

Adjust scroll parameters based on current graphics mode.

```has
extern func GetGraphicsMode() -> int;

proc scroll_full_screen_adaptive(pixels: int) -> int {
    // Scroll the full screen, adjusting coordinates for the current mode
    
    var mode: int = GetGraphicsMode();
    var max_x: int;
    var result: int;
    
    if (mode == 0) {
        // Lores: 320x256x32
        max_x = 319;
    } else if (mode == 1) {
        // Hires: 640x256x16
        max_x = 639;
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

## Example 9: Bounded Scroll with Clipping

Scroll only within valid screen bounds (lores mode).

```has
proc clipped_scroll(x0: int, y0: int, x1: int, y1: int, pixels: int) -> int {
    // Ensure coordinates are within lores bounds
    var clipped_x0: int = x0;
    var clipped_y0: int = y0;
    var clipped_x1: int = x1;
    var clipped_y1: int = y1;
    
    // Clamp to screen bounds
    if (clipped_x0 < 0) {
        clipped_x0 = 0;
    }
    if (clipped_y0 < 0) {
        clipped_y0 = 0;
    }
    if (clipped_x1 > 319) {
        clipped_x1 = 319;
    }
    if (clipped_y1 > 255) {
        clipped_y1 = 255;
    }
    
    // Validate clamped coordinates
    if (clipped_x0 >= clipped_x1 || clipped_y0 >= clipped_y1) {
        return -1;  // Region collapsed to zero size
    }
    
    // Perform scroll with clamped coordinates
    return Scroll(clipped_x0, clipped_y0, clipped_x1, clipped_y1, 0, -1, pixels);
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

### ❌ Rely on Horizontal Scrolling

```has
// DON'T: Horizontal scrolling is not implemented
var result: int = Scroll(0, 0, 319, 255, -1, 0, 16);
// result == 0, but NO SCROLLING ACTUALLY HAPPENED!
```

### ✅ Use Vertical Scrolling

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

1. **Batch scrolls:** If you need to scroll multiple regions, call `Scroll` multiple times rather than trying to optimize into one call.

2. **Use appropriate pixel counts:** Scrolling very small amounts (1–2 pixels) frequently is less efficient than scrolling larger amounts less often.

3. **Call during VBlank:** For smooth animation, call `Scroll` during the VBlank interval to avoid visible tearing or flicker.

4. **Minimize region size:** Scrolling a small sub-region is faster than scrolling the full screen.

5. **Avoid HAM6 mode:** HAM6 is not supported; stick to lores (mode 0) or hires (mode 1).

## See Also

- [SCROLL_FUNCTION.md](SCROLL_FUNCTION.md) – Comprehensive user guide
- [examples/scroll_comprehensive_test.has](../examples/scroll_comprehensive_test.has) – Test suite
- [examples/scroll_function_demo.has](../examples/scroll_function_demo.has) – Additional examples
