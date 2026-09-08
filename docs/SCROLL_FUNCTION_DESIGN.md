# Scroll Function - Extern Declaration Design

## Overview

This document specifies the HAS extern declaration for a graphics Scroll function that scrolls a rectangular screen region by a given number of pixels in horizontal and/or vertical directions.

---

## 1. HAS Extern Declaration

### Full Signature

```has
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                   __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                   __reg(d6) pixels: int) -> int;
```

### Canonical Single-Line Format

```has
extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, __reg(d6) pixels: int) -> int;
```

---

## 2. Parameter Passing Convention

### Register-Based Calling Convention (__reg)

All 7 parameters use dedicated data registers to minimize function call overhead and match the external library's native calling convention:

| Parameter | Register | Type | Purpose |
|-----------|----------|------|---------|
| `x0`      | `d0`     | `int` | Top-left X coordinate of scroll region |
| `y0`      | `d1`     | `int` | Top-left Y coordinate of scroll region |
| `x1`      | `d2`     | `int` | Bottom-right X coordinate of scroll region |
| `y1`      | `d3`     | `int` | Bottom-right Y coordinate of scroll region |
| `hor`     | `d4`     | `int` | Horizontal scroll direction: -1 (left), 0 (no-op), 1 (right) |
| `vert`    | `d5`     | `int` | Vertical scroll direction: -1 (up), 0 (no-op), 1 (down) |
| `pixels`  | `d6`     | `int` | Number of pixels to scroll in specified direction(s) |

### Return Value

- **Register**: `d0`
- **Type**: `int` (32-bit signed)
- **Values**:
  - `0` = Success (scroll operation completed)
  - `-1` = Error (invalid region, incompatible graphics mode, or operation failed)

### Caller Responsibilities

1. **Load parameters into registers**: HAS compiler automatically emits code to load each argument into its assigned register before the `jsr Scroll` instruction.
2. **Save non-volatile registers** (if needed): The caller preserves any non-volatile registers (`d0`-`d7`, `a0`-`a5`) that the caller will use after the `Scroll` call.
3. **Clean up stack** (if applicable): Since all parameters are register-based, no stack cleanup is needed.

### Callee Responsibilities (External Library)

1. **Preserve non-volatile registers**: Save any `d0`-`d7` or `a0`-`a5` registers that the function body uses (except `d0` for the return value).
2. **Return result in `d0`**: Always leave the return value (0 or -1) in the `d0` register before executing `rts`.

---

## 3. Example HAS Code

### Basic Usage

```has
code main:
    extern func Scroll(__reg(d0) x0: int, __reg(d1) y0: int, __reg(d2) x1: int, 
                       __reg(d3) y1: int, __reg(d4) hor: int, __reg(d5) vert: int, 
                       __reg(d6) pixels: int) -> int;

    asm {
        jsr main
        rts
    }

    proc main() -> int {
        var result: int;
        
        // Scroll a region (100, 50) to (200, 150) left by 8 pixels
        result = Scroll(100, 50, 200, 150, -1, 0, 8);
        
        if (result == 0) {
            // Success: region was scrolled left by 8 pixels
            return 0;
        } else {
            // Error: scroll operation failed
            return -1;
        }
    }
```

### Practical Examples

#### Scroll Screen Up

```has
proc scroll_screen_up(pixels: int) -> int {
    // Scroll entire screen up (assuming 320x256 resolution)
    return Scroll(0, 0, 319, 255, 0, -1, pixels);
}
```

#### Scroll Screen Down

```has
proc scroll_screen_down(pixels: int) -> int {
    return Scroll(0, 0, 319, 255, 0, 1, pixels);
}
```

#### Scroll Screen Left

```has
proc scroll_screen_left(pixels: int) -> int {
    return Scroll(0, 0, 319, 255, -1, 0, pixels);
}
```

#### Scroll Screen Right

```has
proc scroll_screen_right(pixels: int) -> int {
    return Scroll(0, 0, 319, 255, 1, 0, pixels);
}
```

#### Scroll Window (Sub-Region)

```has
proc scroll_window(win_x0: int, win_y0: int, win_x1: int, win_y1: int, 
                   dx: int, dy: int, pixels: int) -> int {
    // Scroll a window region diagonally by moving right and down
    // dx, dy: direction indicators (-1, 0, 1)
    return Scroll(win_x0, win_y0, win_x1, win_y1, dx, dy, pixels);
}
```

### With Error Handling

```has
proc safe_scroll_up(pixels: int) -> int {
    var result: int;
    
    // Validate input
    if (pixels < 0 || pixels > 256) {
        return -1;  // Invalid pixel count
    }
    
    // Attempt scroll (top-left 0,0 to bottom-right 319,255 = full screen)
    result = Scroll(0, 0, 319, 255, 0, -1, pixels);
    
    if (result != 0) {
        // Scroll failed (e.g., incompatible graphics mode)
        return -1;
    }
    
    return 0;  // Success
}
```

---

## 4. Generated Assembly

### Example 1: Simple Scroll Call

**HAS Source:**
```has
result = Scroll(100, 50, 200, 150, -1, 0, 8);
```

**Generated Assembly:**
```asm
    move.l #100,d0      ; Load x0 into d0
    move.l #50,d1       ; Load y0 into d1
    move.l #200,d2      ; Load x1 into d2
    move.l #150,d3      ; Load y1 into d3
    move.l #-1,d4       ; Load hor = -1 (left) into d4
    move.l #0,d5        ; Load vert = 0 (no vertical) into d5
    move.l #8,d6        ; Load pixels = 8 into d6
    jsr Scroll          ; Call external Scroll function
    move.l d0,-4(a6)    ; Store return value (success/error) in local 'result'
```

### Example 2: Call with Variables

**HAS Source:**
```has
proc scroll_by_region(x0: int, y0: int, x1: int, y1: int, pixels: int) -> int {
    return Scroll(x0, y0, x1, y1, -1, 0, pixels);  // Scroll left
}
```

**Generated Assembly:**
```asm
scroll_by_region:
    link a6,#0          ; No locals needed
    
    move.l 8(a6),d0     ; Load x0 parameter into d0
    move.l 12(a6),d1    ; Load y0 parameter into d1
    move.l 16(a6),d2    ; Load x1 parameter into d2
    move.l 20(a6),d3    ; Load y1 parameter into d3
    move.l #-1,d4       ; Load hor = -1 (left)
    move.l #0,d5        ; Load vert = 0 (no vertical)
    move.l 24(a6),d6    ; Load pixels parameter into d6
    
    jsr Scroll          ; Call external Scroll function
    
    ; Return value already in d0
    unlk a6
    rts
```

### Example 3: Full Screen Scroll with Error Checking

**HAS Source:**
```has
proc full_screen_scroll_up(pixels: int) -> int {
    var result: int;
    result = Scroll(0, 0, 319, 255, 0, -1, pixels);
    return result;
}
```

**Generated Assembly:**
```asm
full_screen_scroll_up:
    link a6,#-4         ; Allocate 4 bytes for local 'result'
    
    ; Load parameters
    move.l #0,d0        ; x0 = 0
    move.l #0,d1        ; y0 = 0
    move.l #319,d2      ; x1 = 319
    move.l #255,d3      ; y1 = 255
    move.l #0,d4        ; hor = 0 (no horizontal)
    move.l #-1,d5       ; vert = -1 (up)
    move.l 8(a6),d6     ; pixels from parameter
    
    jsr Scroll          ; Call external Scroll function
    
    move.l d0,-4(a6)    ; Store result in local variable
    move.l -4(a6),d0    ; Load result into d0 for return
    
    unlk a6
    rts
```

---

## 5. Constraints and Notes

### Supported Graphics Modes

The Scroll function is only available and functional in:
- **Mode 0** (1-bitplane, 16 colors, 320×256 or 320×512)
- **Mode 1** (2-bitplane, 4 colors, 320×256 or 320×512)
- **Mode 3** (dual playfield) — scrolls only whichever playfield `SetActivePlayfield` last
  selected, leaving the sibling playfield untouched

**Do NOT use in HAM6** — the function will return `-1` (error).

### Region Validation

The function validates the scroll region:
- `x0 < x1`: Left edge must be less than right edge
- `y0 < y1`: Top edge must be less than bottom edge
- All coordinates must be within screen bounds (0–319 for X, 0–255/511 for Y, depending on resolution)
- Invalid regions cause the function to return `-1`

### Direction Parameter Semantics

- **`hor`**: Horizontal scroll direction
  - `-1` = Scroll LEFT (pixels shift to the left)
  - `0` = No horizontal scrolling
  - `1` = Scroll RIGHT (pixels shift to the right)

- **`vert`**: Vertical scroll direction
  - `-1` = Scroll UP (pixels shift upward)
  - `0` = No vertical scrolling
  - `1` = Scroll DOWN (pixels shift downward)

- **`pixels`**: Magnitude of scroll (must be > 0; ignored if both `hor` and `vert` are 0)

### Blitter Requirement

The Scroll function uses the Amiga **Blitter** for high-performance region scrolling. If the Blitter is busy or unavailable, the function may:
- Busy-wait until the Blitter is free (blocking call)
- Or return `-1` (error) if a timeout occurs

**Plan accordingly**: Scroll calls may have variable latency in real-time code.

### Stack Frame and ABI

- **Frame Register**: The external Scroll function may not use frame pointers (`a6`). Callers should not rely on frame pointer preservation.
- **Return Address**: Standard 68000 ABI — `rts` pops the return address from the stack.
- **Preserved Registers**: Data registers `d1`–`d7` and address registers `a0`–`a5` are preserved unless modified by the callee.

### Calling Overhead

- **Register parameters**: No stack push/pop overhead.
- **Call instruction**: Single `jsr Scroll` instruction.
- **No prologue/epilogue**: Caller is responsible for saving/restoring non-volatile registers (if needed after the call).

### Example: Optimized Repeated Scrolls

If you need to scroll the same region multiple times, cache the region coordinates:

```has
proc animate_scroll(pixels_per_frame: int, num_frames: int) -> int {
    var x0: int = 50;
    var y0: int = 50;
    var x1: int = 269;  // 50 + 220 (window width)
    var y1: int = 205;  // 50 + 156 (window height)
    var frame: int = 0;
    
    while (frame < num_frames) {
        if (Scroll(x0, y0, x1, y1, -1, 0, pixels_per_frame) != 0) {
            return -1;  // Error
        }
        frame = frame + 1;
    }
    
    return 0;  // Success
}
```

This pattern minimizes register setup overhead per frame.

---

## 6. Assembly Library Implementation Template

The external Scroll function should be implemented in VASM with this signature:

```asm
    XDEF Scroll
    
Scroll:
    ; Parameters in registers:
    ; d0 = x0 (top-left X)
    ; d1 = y0 (top-left Y)
    ; d2 = x1 (bottom-right X)
    ; d3 = y1 (bottom-right Y)
    ; d4 = hor (-1/0/1 for left/none/right)
    ; d5 = vert (-1/0/1 for up/none/down)
    ; d6 = pixels (scroll magnitude)
    ;
    ; Returns:
    ; d0 = 0 (success) or -1 (error)
    
    ; Validate region: x0 < x1 and y0 < y1
    cmp.l d2,d0         ; Compare x0 vs x1
    bge .error          ; Branch if x0 >= x1 (invalid)
    
    cmp.l d3,d1         ; Compare y0 vs y1
    bge .error          ; Branch if y0 >= y1 (invalid)
    
    ; TODO: Implement blitter-based scroll logic
    ; TODO: Handle hor/vert direction flags
    ; TODO: Validate graphics mode (Mode 0 or 1 only)
    
    move.l #0,d0        ; Return 0 (success)
    rts
    
.error:
    move.l #-1,d0       ; Return -1 (error)
    rts
```

---

## 7. Summary

| Aspect | Details |
|--------|---------|
| **Declaration** | `extern func Scroll(__reg(d0) x0, __reg(d1) y0, __reg(d2) x1, __reg(d3) y1, __reg(d4) hor, __reg(d5) vert, __reg(d6) pixels) -> int;` |
| **Parameters** | 7 × 32-bit integers, all in data registers d0–d6 |
| **Return Value** | 32-bit integer in d0: 0 (success) or -1 (error) |
| **Calling Convention** | Register-based (no stack arguments) |
| **Supported Modes** | Mode 0, Mode 1, Mode 3 (dual playfield, active playfield only); no HAM6 |
| **Region Constraints** | `x0 < x1`, `y0 < y1`, coordinates within screen bounds |
| **Performance** | Uses Blitter; may block if Blitter is busy |

---

## Appendix: Differences from Stack-Based Calling Convention

### With Stack Parameters (Not Recommended)

```has
// Stack-based version (less efficient)
extern func Scroll_Stack(x0: int, y0: int, x1: int, y1: int, 
                         hor: int, vert: int, pixels: int) -> int;
```

**Generated Assembly:**
```asm
    move.l #8,-(a7)     ; Push pixels (rightmost)
    move.l #0,-(a7)     ; Push vert
    move.l #-1,-(a7)    ; Push hor
    move.l #150,-(a7)   ; Push y1
    move.l #200,-(a7)   ; Push x1
    move.l #50,-(a7)    ; Push y0
    move.l #100,-(a7)   ; Push x0 (leftmost)
    jsr Scroll_Stack
    add.l #28,a7        ; Clean up 7 × 4-byte stack args
```

**Overhead**: 7 push + 1 jsr + 1 stack cleanup = ~32 instruction bytes (vs. 7 move + 1 jsr = ~20 bytes with register parameters).

### Register-Based Version (Recommended)

```asm
    move.l #100,d0      ; x0
    move.l #50,d1       ; y0
    move.l #200,d2      ; x1
    move.l #150,d3      ; y1
    move.l #-1,d4       ; hor
    move.l #0,d5        ; vert
    move.l #8,d6        ; pixels
    jsr Scroll          ; 8 × 4-byte moves + 1 jsr = ~20 bytes
```

**Benefit**: ~37% less instruction overhead + zero stack manipulation.

---

## Appendix: ScrollHorizontalScreen Uses a Different (Stack) Convention

`ScrollHorizontalScreen(px: int) -> int` is a separate hardware-register function (sets `BPLCON1`
fine-scroll directly) that intentionally does **not** follow this document's register-based `__reg`
design - it takes its single `px` argument on the stack (`8(a6)`), matching the plain calling
convention used by `SetActivePlayfield`/`ClearPlayfield`/`SetFont` rather than `Scroll`'s 7-register
ABI. A single-argument function has no register-pressure motivation for a custom ABI, so it follows
the library's default convention instead. See
[SCROLL_FUNCTION.md](SCROLL_FUNCTION.md#scrollhorizontalscreen-hardware-fine-scroll) for its full
behavior.
