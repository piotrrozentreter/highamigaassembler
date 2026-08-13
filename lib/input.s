;****************************************************************
; Mouse input
;
; (c) 2024 Stefano Coppi
; (c) 2026 by Piotr Rozentreter (Rozsoft)
;****************************************************************

    include "hardware.i"
            
;****************************************************************
; VARIABLES
;****************************************************************

        SECTION    input_data,DATA
        EVEN
			
mouse_x     dc.w       0                    ; old mouse position (word to avoid 8-bit wrap)
mouse_y     dc.w       0
mouse_dx    dc.w       0                    ; difference between current and old position of mouse
mouse_dy    dc.w       0
mouse_lbtn  dc.w       0                    ; state of left mouse button: 1 pressed, 0 not pressed
mouse_rbtn  dc.w       0                    ; state of left right button: 1 pressed, 0 not pressed
mouse_lbtn_prev      dc.w 0                 ; previous left mouse button state
mouse_lbtn_pressed   dc.w 0                 ; left mouse button press edge
mouse_lbtn_released  dc.w 0                 ; left mouse button release edge
mouse_rbtn_prev      dc.w 0                 ; previous right mouse button state
mouse_rbtn_pressed   dc.w 0                 ; right mouse button press edge
mouse_rbtn_released  dc.w 0                 ; right mouse button release edge
            SECTION    code,CODE

;****************************************************************
; Public API
;****************************************************************



;****************************************************************
; SUBROUTINES
;****************************************************************


;----------------------------------------------------------------
; Function: ReadJoystick
; Input: none
; Output: d0,d1=joystick state bits
; Description: Reads joystick 0 direction state from JOY0DAT.
; Notes: Returns the raw decoded axis state used by existing callers.
;----------------------------------------------------------------
            xdef       ReadJoystick
ReadJoystick:
            move.l  JOY0DAT(a5),d0
            and.l   #$03030303,d0
            move.l  d0,d1
            add.l   d1,d1
            add.l   #$01010101,d0
            add.l   d1,d0
            rts

;----------------------------------------------------------------
; Function: ReadJoystickFire
; Input: none
; Output: d0=1 if pressed, 0 otherwise
; Description: Reads joystick 0 fire button state.
; Notes: Uses CIAA button input for the fire trigger.
;----------------------------------------------------------------
            xdef ReadJoystickFire
ReadJoystickFire:
            clr.l d0
            btst.b #7,$bfe001
            bne.s .no_fire
            move.b #1,d0
.no_fire:
            rts

;----------------------------------------------------------------
; Function: ReadMouse
; Input: none
; Output: d0,d1=updated mouse state
; Description: Updates mouse deltas, absolute position, and button state.
; Notes: Keeps internal mouse_x/mouse_y/mouse_dx/mouse_dy in sync.
;----------------------------------------------------------------
            xdef       ReadMouse
ReadMouse:
            movem.l    d0-d1,-(sp)


            move.b     JOY0DAT(a5),d1       ; reads mouse vertical position (8-bit counter)
            ext.w      d1                   ; sign-extend to word
            move.w     d1,d0                ; copy current
            sub.w      mouse_y,d1           ; delta = cur - prev
            cmp.w      #-128,d1             ; handle wrap-around: if delta < -128, add 256
            bge.s      .no_v_underflow
            add.w      #256,d1
.no_v_underflow:
            cmp.w      #127,d1              ; if delta > 127, subtract 256
            ble.s      .no_v_overflow
            sub.w      #256,d1
.no_v_overflow:
            move.w     d1,mouse_dy          ; saves mouse_dy (word)
            move.w     d0,mouse_y           ; saves position (word)

            move.b     JOY0DAT+1(a5),d1     ; reads mouse horizontal position (8-bit counter)
            ext.w      d1                   ; sign-extend to word
            move.w     d1,d0                ; copy current
            sub.w      mouse_x,d1           ; delta = cur - prev
            cmp.w      #-128,d1             ; handle wrap-around: if delta < -128, add 256
            bge.s      .no_h_underflow
            add.w      #256,d1
.no_h_underflow:
            cmp.w      #127,d1              ; if delta > 127, subtract 256
            ble.s      .no_h_overflow
            sub.w      #256,d1
.no_h_overflow:
            move.w     d1,mouse_dx          ; saves mouse_dx (word)
            move.w     d0,mouse_x           ; saves position (word)

            move.w     mouse_lbtn,mouse_lbtn_prev
            move.w     mouse_rbtn,mouse_rbtn_prev

; if bit 6 of CIAAPRA = 0, then left mouse button is pressed
            btst       #6,CIAAPRA
            beq        .lbtn_pressed
            clr.w      mouse_lbtn
            bra        .check_rbtn 
.lbtn_pressed:
            move.w     #1,mouse_lbtn

; if bit 2 of POTINP = 0, then right mouse button is pressed
.check_rbtn:
            btst       #2,POTINP(a5)
            beq        .rbtn_pressed
            clr.w      mouse_rbtn
            bra        .return
.rbtn_pressed:
            move.w     #1,mouse_rbtn            

.update_btn_edges:
            move.w     mouse_lbtn_prev,d0
            not.w      d0
            and.w      mouse_lbtn,d0
            move.w     d0,mouse_lbtn_pressed
            move.w     mouse_lbtn,d0
            not.w      d0
            and.w      mouse_lbtn_prev,d0
            move.w     d0,mouse_lbtn_released

            move.w     mouse_rbtn_prev,d0
            not.w      d0
            and.w      mouse_rbtn,d0
            move.w     d0,mouse_rbtn_pressed
            move.w     mouse_rbtn,d0
            not.w      d0
            and.w      mouse_rbtn_prev,d0
            move.w     d0,mouse_rbtn_released

.return:
            movem.l    (sp)+,d0-d1
            rts

;----------------------------------------------------------------
; Function: GetMouseX
; Input: none
; Output: d0=mouse X
; Description: Returns the current accumulated mouse X position.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseX
GetMouseX:
            move.w     mouse_x,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseY
; Input: none
; Output: d0=mouse Y
; Description: Returns the current accumulated mouse Y position.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseY
GetMouseY:
            move.w     mouse_y,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseDX
; Input: none
; Output: d0=mouse delta X
; Description: Returns the latest mouse X delta.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseDX
GetMouseDX:
            move.w     mouse_dx,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseDY
; Input: none
; Output: d0=mouse delta Y
; Description: Returns the latest mouse Y delta.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseDY
GetMouseDY:
            move.w     mouse_dy,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseLBtn
; Input: none
; Output: d0=left mouse button state
; Description: Returns the current left mouse button state.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseLBtn
GetMouseLBtn:
            move.w     mouse_lbtn,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseRBtn
; Input: none
; Output: d0=right mouse button state
; Description: Returns the current right mouse button state.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseRBtn
GetMouseRBtn:
            move.w     mouse_rbtn,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseLBtnPressed
; Input: none
; Output: d0=1 on left mouse button press edge, 0 otherwise
; Description: Returns the left mouse button press edge from the latest ReadMouse call.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseLBtnPressed
GetMouseLBtnPressed:
            move.w     mouse_lbtn_pressed,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseLBtnReleased
; Input: none
; Output: d0=1 on left mouse button release edge, 0 otherwise
; Description: Returns the left mouse button release edge from the latest ReadMouse call.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseLBtnReleased
GetMouseLBtnReleased:
            move.w     mouse_lbtn_released,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseRBtnPressed
; Input: none
; Output: d0=1 on right mouse button press edge, 0 otherwise
; Description: Returns the right mouse button press edge from the latest ReadMouse call.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseRBtnPressed
GetMouseRBtnPressed:
            move.w     mouse_rbtn_pressed,d0
            ext.l      d0
            rts

;----------------------------------------------------------------
; Function: GetMouseRBtnReleased
; Input: none
; Output: d0=1 on right mouse button release edge, 0 otherwise
; Description: Returns the right mouse button release edge from the latest ReadMouse call.
; Notes: Value is sign-extended to long.
;----------------------------------------------------------------
            xdef       GetMouseRBtnReleased
GetMouseRBtnReleased:
            move.w     mouse_rbtn_released,d0
            ext.l      d0
            rts
