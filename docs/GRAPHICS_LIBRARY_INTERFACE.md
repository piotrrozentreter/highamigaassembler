# Interfacing HAS with graphics.s Library

## Overview

The `lib/graphics.s` file provides Amiga graphics functions that can be called from HAS code. The library uses a **stack-based calling convention** which is **100% compatible** with HAS's default calling convention.

## Calling Convention Compatibility

### graphics.s Convention
- Uses `link a6,#0` to set up stack frame
- Arguments accessed at `8(a6)`, `12(a6)`, `16(a6)`, etc.
- Caller pushes arguments in reverse order
- Caller cleans up stack after call

### HAS Default Convention
- Exactly the same! HAS generates:
  - `link a6,#-N` for stack frame (N = local variable space)
  - Pushes arguments in reverse order before `jsr`
  - Cleans up stack with `addq.l #bytes,a7` after call

**Result:** You can call graphics.s functions directly from HAS with `extern func` declarations!

## How to Use graphics.s from HAS

### Step 1: Declare External Functions

```has
code main:
    // Declare functions from graphics.s as external
    extern func SetGraphicsMode(mode: int) -> int;
    extern func ClearScreen() -> int;
    extern func SetPixel(x: int, y: int, color: int) -> int;
    extern func Text(x: int, y: int, msg: int, color: int) -> int;
    extern func Print(msg: int, color: int) -> int;
    extern func SwapScreen() -> int;
    extern func UpdateCopperList() -> int;
    extern func SetFont(font_ptr: int) -> int;
    extern func SetTextMode(mode: int) -> int;
    extern func SetColor(idx: int, value: int) -> int;
    extern func ToRGB(r: int, g: int, b: int) -> int;
```

### Step 2: Call the Functions

```has
    proc main() -> int {
        var result: int;
        
        // Initialize graphics mode 0 (320x256x32 colors)
        result = SetGraphicsMode(0);
        
        // Clear screen
        call ClearScreen();
        
        // Draw a pixel at (100, 100) in color 31 (white)
        call SetPixel(100, 100, 31);
        
        // Update display
        call UpdateCopperList();
        call SwapScreen();
        
        return 0;
    }
```

### Step 3: Link with graphics.s

When assembling and linking, include graphics.s:

```bash
# Compile HAS source
python3 -m hasc.cli my_program.has -o my_program.s

# Assemble both files
vasmm68k_mot -Fhunk -o my_program.o my_program.s
vasmm68k_mot -Fhunk -o graphics.o lib/graphics.s

# Link together
vlink -bamigahunk -o my_program my_program.o graphics.o
```

## Available Functions

### Graphics Initialization

#### SetGraphicsMode(mode: int) -> int
- **mode 0**: 320x256 resolution, 32 colors (5 bitplanes)
- **mode 1**: 640x256 resolution, 16 colors (4 bitplanes, hires)
- **mode 2**: 320x256 resolution, HAM6 (6 bitplanes, single-buffered)
- Returns 0 on success, -1 on error (including when the mode's screen buffer or copper list was disabled at assembly time - see [Opt-in Memory Savings](#opt-in-memory-savings-disabling-unused-screen-buffers-and-copper-lists) below)

```has
var result: int = SetGraphicsMode(0);  // 320x256x32
```

### Screen Management

#### ClearScreen() -> int
Clears the current screen buffer to black.

```has
call ClearScreen();
```

#### SwapScreen() -> int
Swaps between double buffers (toggles between screen1 and screen2).

```has
call SwapScreen();
```

#### UpdateCopperList() -> int
Updates the copper list with current screen pointers and sprite data. Call after SwapScreen() during VBlank.

```has
call UpdateCopperList();
```

### Drawing Functions

#### SetPixel(x: int, y: int, color: int) -> int
Draws a pixel at (x, y) with the specified color.
- **Lores mode**: x=0-319, y=0-255, color=0-31
- **Hires mode**: x=0-639, y=0-255, color=0-15
- Returns 0 on success, -1 if coordinates/color out of bounds

```has
call SetPixel(160, 128, 31);  // White pixel at center
```

### Text Functions

#### SetFont(font_ptr: int) -> int
Sets the current font for text rendering. `font_ptr` should point to font bitmap data.

```has
var font_addr: int = 0x80000;  // Example address
call SetFont(font_addr);
```

#### Print(msg: int, color: int) -> int
Prints a null-terminated string at the current cursor position.
- **msg**: Pointer to null-terminated string
- **color**: Text color (0-31 lores, 0-15 hires)

```has
// Note: Requires assembly block for string data
asm {
my_message:
    dc.b "Hello!",0
    even
}
var msg_ptr: int = &my_message;  // Address-of operator
call Print(msg_ptr, 31);
```

#### Text(x: int, y: int, msg: int, color: int) -> int
Prints text at specific character coordinates (not pixel coordinates).
- **x**: Character column (0-39 lores, 0-79 hires)
- **y**: Character row (0-31)
- **msg**: Pointer to null-terminated string
- **color**: Text color

```has
call Text(10, 5, msg_ptr, 31);  // Print at column 10, row 5
```

#### SetTextMode(mode: int) -> int
Controls whether `Print`/`Text` draw glyphs transparently or with an opaque background.
- **mode 0** (default): transparent - only the glyph foreground pixels are drawn; existing background pixels in the 8x8 cell are left untouched.
- **mode 1**: opaque - the entire 8x8 glyph cell background is cleared to color 0 (across all bitplanes) before the glyph foreground is drawn.

```has
// Draw HUD text with a solid background, then restore default transparent text
call SetTextMode(1);
call Text(0, 0, hud_msg_ptr, 31);
call SetTextMode(0);
```

### Color Functions

#### SetColor(idx: int, value: int) -> int
Sets a palette color.
- **idx**: Color index (0-31 lores, 0-15 hires)
- **value**: 12-bit Amiga color value (0x0RGB format)
- Returns 0 on success, -1 if index out of range

```has
call SetColor(1, 0x0F00);  // Set color 1 to bright red
```

#### ToRGB(r: int, g: int, b: int) -> int
Converts RGB components to 12-bit Amiga color format.
- **r, g, b**: Color components (0-15)
- Returns: 12-bit color value (r<<8 | g<<4 | b)

```has
var color: int = ToRGB(15, 0, 0);  // Bright red
call SetColor(1, color);
```

## Complete Example

```has
code main:
    extern func SetGraphicsMode(mode: int) -> int;
    extern func ClearScreen() -> int;
    extern func SetPixel(x: int, y: int, color: int) -> int;
    extern func UpdateCopperList() -> int;
    extern func SwapScreen() -> int;
    
    public main;
    
    proc main() -> int {
        var x: int;
        var y: int;
        var color: int;
        
        // Initialize lores graphics
        call SetGraphicsMode(0);
        call ClearScreen();
        
        // Draw a colorful pattern
        for y = 0 to 255 {
            for x = 0 to 319 {
                color = (x + y) & 31;  // Color based on position
                call SetPixel(x, y, color);
            }
        }
        
        // Display the result
        call UpdateCopperList();
        call SwapScreen();
        
        return 0;
    }
```

## Working with Strings

Currently, HAS doesn't have string literal support in expressions. To pass strings to Print/Text, use assembly blocks:

```has
code main:
    extern func Print(msg: int, color: int) -> int;
    
    proc main() -> int {
        // Assembly block with string data
        asm {
greeting:
        dc.b "Welcome to HAS!",0
        even
        
        ; Call Print directly from assembly
        move.l #31,-(a7)        ; color
        lea greeting,a0
        move.l a0,-(a7)         ; string pointer
        jsr Print
        addq.l #8,a7            ; cleanup
        }
        
        return 0;
    }
```

## Opt-in Memory Savings: Disabling Unused Screen Buffers and Copper Lists

By default, `lib/graphics.s` reserves chip-RAM screen buffers for all three
supported graphics modes in its `screen` `bss_c` section (~327,680 bytes
total) and emits the mode-specific copper lists in the `copper` section.

| Mode | Buffers | Size each | Total |
|------|---------|-----------|-------|
| 0 - lores 320x256x32 | `gfx_screen1`, `gfx_screen2` | 51,200 bytes | 102,400 bytes |
| 1 - hires 640x256x16 | `gfx_screen1_hires`, `gfx_screen2_hires` | 81,920 bytes | 163,840 bytes |
| 2 - HAM6 320x256 | `gfx_screen1_ham6` (single-buffered) | 61,440 bytes | 61,440 bytes |

If your application only calls `SetGraphicsMode()` with a subset of these
modes, you can opt out of reserving the unused buffers by defining one or
more of these constants when assembling `lib/graphics.s` with vasm:

- `DISABLE_320x256` - drops the lores mode 0 buffers (`gfx_screen1`, `gfx_screen2`)
- `DISABLE_640x256` - drops the hires mode 1 buffers (`gfx_screen1_hires`, `gfx_screen2_hires`)
- `DISABLE_HAM` - drops the HAM6 mode 2 buffer (`gfx_screen1_ham6`)

Each flag also omits that mode's copper list and its palette, bitplane-pointer,
and sprite-pointer entries. The copper-list labels remain defined as inert
placeholders, so code still assembles and links when a mode is disabled.

```bash
# Only using lores mode 0: drop hires and HAM6 buffers to save ~225,280 bytes
vasmm68k_mot -Fhunk -D DISABLE_640x256=1 -D DISABLE_HAM=1 -o graphics.o lib/graphics.s
```

Any combination of the three can be defined. Defining all three shrinks the
entire `screen` section down to a small placeholder.

**Safety guarantees:**

- The buffer labels (`gfx_screen1`, `gfx_screen2`, `gfx_screen1_hires`,
  `gfx_screen2_hires`, `gfx_screen1_ham6`) always stay defined regardless of
  which `DISABLE_*` constants are set, so other code in `graphics.s` that
  references them still assembles and links normally.
- `SetGraphicsMode()` refuses to activate a mode whose buffer was disabled at
  assembly time: it returns `d0 = -1` (its existing error code) instead of
  proceeding to use the shrunk placeholder buffer. Callers must still check
  the return value (or simply avoid calling a disabled mode) - the guard
  prevents memory corruption, but it does not make calling a disabled mode
  meaningful.

**Placeholder caveat:** a disabled buffer is not shrunk to `ds.b 0` - it
reserves a 2-byte placeholder instead. Assembling with all three constants
defined previously produced a fully empty `bss_c` `screen` section, which
crashed `vlink` (V0.17a) with an access violation. Reserving a tiny 2-byte
placeholder per disabled buffer avoids that linker defect while still saving
nearly all of the chip RAM.

## Important Notes

1. **Chip RAM Requirement**: The screen buffers in graphics.s are in CHIP RAM (required for Amiga display hardware). Make sure your linker script places the `screen_data` section in chip RAM.

2. **Custom Register Base**: graphics.s expects register `a5` to contain the custom chip base address ($DFF000). Initialize this before calling graphics functions:
   ```asm
   lea $DFF000,a5
   ```

3. **Return Values**: Most functions return 0 on success, -1 on error. Check return values when appropriate.

4. **Pointer Arguments**: Functions that take string pointers (Print, Text) expect actual memory addresses. You'll need to use assembly blocks or data sections to define strings.

5. **Coordinate Systems**:
   - **SetPixel**: Pixel coordinates (0-319/639 x 0-255)
   - **Text**: Character coordinates (0-39/79 x 0-31, each char is 8x8 pixels)

## Compilation Workflow

1. Write HAS code with extern declarations
2. Compile HAS to assembly: `python3 -m hasc.cli program.has -o program.s`
3. Assemble both files: `vasmm68k_mot -Fhunk program.s` and `lib/graphics.s`
4. Link together: `vlink -bamigahunk -o program program.o graphics.o`
5. Run on Amiga or emulator

## Conclusion

The graphics.s library is **fully compatible** with HAS's calling convention. You can:
- ✅ Declare functions as `extern func`
- ✅ Call them like any other function
- ✅ Pass arguments normally
- ✅ Receive return values in variables
- ✅ Mix HAS code and assembly blocks seamlessly

The only limitation is string handling, which currently requires assembly blocks for string definitions.
