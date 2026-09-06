; ============================================================================
; Scroll Function - Reference VASM Implementation Template
; 
; This file shows a template for implementing the Scroll function in VASM
; for linking with HAS-compiled code.
;
; See: SCROLL_FUNCTION_DESIGN.md for the calling convention specification
; ============================================================================

    XDEF Scroll
    XDEF ScrollInit

; ============================================================================
; Scroll Function
;
; Input:  d0 = x0 (top-left X coordinate, 0-319)
;         d1 = y0 (top-left Y coordinate, 0-255 or 0-511)
;         d2 = x1 (bottom-right X coordinate, must be > x0)
;         d3 = y1 (bottom-right Y coordinate, must be > y0)
;         d4 = hor (horizontal direction: -1=left, 0=none, 1=right)
;         d5 = vert (vertical direction: -1=up, 0=none, 1=down)
;         d6 = pixels (magnitude of scroll in pixels)
;
; Output: d0 = 0 on success, -1 on error
;         (other registers preserved)
;
; Description:
;   Scrolls a rectangular region of the screen by the specified number
;   of pixels in the given horizontal/vertical direction.
;   Uses the Amiga Blitter for acceleration.
;
; Notes:
;   - Only works in Mode 0 (1-bitplane) and Mode 1 (2-bitplane)
;   - Returns -1 for HAM6 or other unsupported graphics modes
;   - Region coordinates must satisfy: x0 < x1, y0 < y1
;   - Coordinates must be within screen bounds
;   - May busy-wait if Blitter is in use
;
; ============================================================================

Scroll:
    ; Save non-volatile registers we'll use (except d0 for return value)
    move.l  d2,-(a7)        ; Save d2
    move.l  d3,-(a7)        ; Save d3
    move.l  a5,-(a7)        ; Save a5
    
    ; --- Step 1: Validate Input Region ---
    
    ; Check: x0 < x1
    cmp.l   d2,d0           ; Compare x0 vs x1
    bge     .error_invalid  ; Branch if x0 >= x1
    
    ; Check: y0 < y1
    cmp.l   d3,d1           ; Compare y0 vs y1
    bge     .error_invalid  ; Branch if y0 >= y1
    
    ; Check: pixels > 0
    tst.l   d6
    ble     .error_invalid  ; Branch if pixels <= 0
    
    ; --- Step 2: Validate Graphics Mode ---
    ; (Pseudo-code: would need to check Amiga graphics library state)
    ;
    ; In real implementation:
    ;   - Read graphics.library variables to get current mode
    ;   - Check if mode is Mode 0 (1-bitplane) or Mode 1 (2-bitplane)
    ;   - Return -1 if mode is HAM6 or other unsupported type
    
    ; For now, assume mode is valid; real code would validate here
    
    ; --- Step 3: Calculate Blitter Parameters ---
    ; (Pseudo-code: would set up Blitter A/B/C/D registers)
    ;
    ; Typical Blitter-based scroll:
    ;   - Set source/dest rectangular regions
    ;   - Set horizontal/vertical shift amounts
    ;   - Configure Blitter control registers
    ;   - Wait for Blitter to complete
    
    ; --- Step 4: Set Up Blitter (Example Framework) ---
    
    ; Get Blitter custom chip address (if available via OS)
    ; movea.l ChipBase,a5    ; Pseudo-code: load blitter base
    
    ; Calculate pitch (bytes per scanline) - depends on graphics mode
    ; For Mode 0/1: typically 40 bytes (320 pixels / 8)
    move.l  #40,d3          ; Default bitplane pitch
    
    ; Calculate source/destination addresses
    ; (Would convert x0,y0,x1,y1 to actual memory addresses)
    
    ; --- Step 5: Execute Blitter Scroll ---
    
    ; Write to Blitter control registers (pseudo-code):
    ; - Set horizontal scroll amount (hor * pixels)
    ; - Set vertical scroll amount (vert * pixels)
    ; - Set region dimensions
    ; - Set BLTCON0/BLTCON1 for scroll operation
    ; - Write BLTSIZH/BLTSIZW to start operation
    
    ; --- Step 6: Wait for Blitter to Complete ---
    
    ; Poll BLTWAIT or use interrupt (would be OS-dependent)
    
    ; --- Step 7: Return Success ---
    
    move.l  #0,d0           ; Return 0 (success)
    
    ; Restore saved registers
    move.l  (a7)+,a5
    move.l  (a7)+,d3
    move.l  (a7)+,d2
    rts
    
    ; --- Error Path: Invalid Region ---
    
.error_invalid:
    move.l  #-1,d0          ; Return -1 (error)
    
    ; Restore saved registers
    move.l  (a7)+,a5
    move.l  (a7)+,d3
    move.l  (a7)+,d2
    rts


; ============================================================================
; ScrollInit - Initialize Scroll Function (Optional)
;
; Input:  (none)
; Output: d0 = 0 on success, -1 on error
;
; Description:
;   Optional initialization function for Scroll.
;   May set up graphics.library pointers, validate system state, etc.
;   Call this once before using Scroll.
;
; ============================================================================

ScrollInit:
    ; Example: Set up pointers to graphics.library
    ;   (In real implementation, would initialize Blitter state)
    
    move.l  #0,d0           ; Return 0 (success)
    rts


; ============================================================================
; Notes on Full Implementation
;
; A complete Scroll implementation would need to:
;
; 1. **Detect Graphics Mode**
;    - Read graphics.library (or custom) state
;    - Verify mode is 0 (1-bitplane) or 1 (2-bitplane)
;    - Return -1 for HAM6 or other modes
;
; 2. **Calculate Blitter Parameters**
;    - Convert logical screen coordinates to bitplane addresses
;    - Calculate horizontal/vertical shift amounts
;    - Set up source/destination regions
;
; 3. **Configure Blitter Hardware**
;    - BLTCON0: Set A-shift, B-shift, function select
;    - BLTCON1: Set BLTAFWM/BLTALWM for edge masks
;    - BLTSIZH/BLTSIZW: Set region size
;    - BLTAPT/BLTBPT/BLTDPT: Set source/dest addresses
;
; 4. **Handle Blitter Wait**
;    - Poll BLTWAIT register (busy-wait)
;    - Or use interrupt-based notification
;    - Or use TakeSystem/GiveSystem for full control
;
; 5. **Edge Cases**
;    - Empty region (x0 == x1 or y0 == y1)
;    - Out-of-bounds coordinates
;    - Diagonal scrolls (both hor and vert non-zero)
;    - Single-bitplane modes (no interleave)
;
; ============================================================================
