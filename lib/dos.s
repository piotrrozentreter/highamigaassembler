; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; dos.s - Minimal AmigaDOS CLI output helpers for HAS runtime (Motorola 68000)
;
; Design:
; - Thin, self-contained wrappers for writing text/numbers to the current
;   CLI/Workbench stdout stream via dos.library Write().
; - dos.library base and the cached Output() handle are managed explicitly
;   with InitDOS/CloseDOS, independent of lib/fileio.s and lib/debug.s
;   (each module caches its own dos.library base, by existing convention).
; - Byte-scanning (PrintOut) and decimal formatting (PrintNum) are
;   implemented inline to keep this module free of cross-lib dependencies.
;
; Calling convention:
; - All routines use link a6,#0 (or a small local frame) and stack args at
;   8(a6), 12(a6), ... since HAS always pushes int/pointer args as 32-bit
;   longs regardless of declared size.
; - Returns in d0 unless stated otherwise.
;
; Public API:
;   InitDOS() -> int                       ; 0 success, -1 fail (idempotent)
;   CloseDOS() -> int                      ; 0 always (idempotent)
;   PrintOut(msg: ptr) -> int              ; bytes written or -1
;   PrintOutLen(msg: ptr, length: int) -> int ; bytes written or -1
;   PrintNum(value: int) -> int            ; bytes written or -1
;
; =============================================================================

    include "hardware.i"
    include "exec_lib.i"

    SECTION dos_data,DATA

DOS_LVO_OUTPUT      EQU -60
DOS_LVO_WRITE        EQU -48

dos_lib_name:
    dc.b "dos.library",0
    even

dos_lib_base:
    dc.l 0

dos_out_handle:
    dc.l 0

dos_num_buffer:
    ds.b 16

    SECTION dos_code,CODE

; =============================================================================
; Public API
; =============================================================================

    XDEF InitDOS
    XDEF CloseDOS
    XDEF PrintOut
    XDEF PrintOutLen
    XDEF PrintNum

; -----------------------------------------------------------------------------
; Function: InitDOS
; Input: none
; Output: d0=0 success, d0=-1 failure
; Description: Opens dos.library and caches its base plus the current
;              CLI/Workbench stdout handle (via DOS Output()).
; Notes: Safe to call multiple times; repeated success is a no-op.
; -----------------------------------------------------------------------------
InitDOS:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l dos_lib_base,d0
    tst.l d0
    bne .id_ok

    move.l ExecBase,a6
    lea dos_lib_name,a1
    jsr _LVOOldOpenLibrary(a6)
    move.l d0,dos_lib_base
    tst.l d0
    beq .id_fail

    move.l d0,a6
    jsr DOS_LVO_OUTPUT(a6)
    move.l d0,dos_out_handle

.id_ok:
    moveq #0,d0
    bra .id_done

.id_fail:
    moveq #-1,d0

.id_done:
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: CloseDOS
; Input: none
; Output: d0=0
; Description: Closes the cached dos.library base if currently open and
;              clears the cached base and stdout handle.
; Notes: Idempotent; calling when not initialized is harmless.
; -----------------------------------------------------------------------------
CloseDOS:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l dos_lib_base,d0
    tst.l d0
    beq .cd_done

    move.l d0,a1
    move.l ExecBase,a6
    jsr _LVOCloseLibrary(a6)
    clr.l dos_lib_base
    clr.l dos_out_handle

.cd_done:
    moveq #0,d0
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PrintOut
; Input: 8(a6)=msg_ptr (NUL-terminated string)
; Output: d0=bytes written, or -1 if DOS is not initialized or Write() failed
; Description: Scans msg_ptr for its length, then writes it via DOS Write()
;              to the cached CLI/Workbench stdout handle.
; Notes: Requires InitDOS() success before use.
; -----------------------------------------------------------------------------
PrintOut:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l dos_lib_base,d0
    tst.l d0
    beq .po_no_dos

    move.l 8(a6),a0
    moveq #0,d3

.po_scan:
    tst.b (a0)
    beq .po_scan_done
    addq.l #1,a0
    addq.l #1,d3
    bra .po_scan

.po_scan_done:
    move.l dos_out_handle,d1
    move.l 8(a6),d2
    move.l dos_lib_base,a6
    jsr DOS_LVO_WRITE(a6)
    bra .po_done

.po_no_dos:
    moveq #-1,d0

.po_done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PrintOutLen
; Input: 8(a6)=msg_ptr, 12(a6)=length
; Output: d0=bytes written, or -1 if DOS is not initialized or Write() failed
; Description: Writes exactly `length` bytes without scanning for a NUL.
; Notes: Requires InitDOS() success before use.
; -----------------------------------------------------------------------------
PrintOutLen:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l dos_lib_base,d0
    tst.l d0
    beq .pol_no_dos

    move.l dos_out_handle,d1
    move.l 8(a6),d2
    move.l 12(a6),d3
    move.l dos_lib_base,a6
    jsr DOS_LVO_WRITE(a6)
    bra .pol_done

.pol_no_dos:
    moveq #-1,d0

.pol_done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PrintNum
; Input: 8(a6)=value (signed 32-bit)
; Output: d0=bytes written, or -1 if DOS is not initialized or Write() failed
; Description: Formats value as signed decimal into an internal scratch
;              buffer (no trailing newline) and writes it via DOS Write().
; Notes: Uses a 68000-compatible shift/subtract 32-bit divide-by-10, since
;        68000 lacks a 32-bit hardware divide instruction.
; -----------------------------------------------------------------------------
PrintNum:
    link a6,#-16
    movem.l d1-d7/a0-a6,-(sp)

    move.l dos_lib_base,d0
    tst.l d0
    beq .pn_no_dos

    move.l 8(a6),d1
    moveq #0,d2
    tst.l d1
    bpl .pn_positive
    neg.l d1
    moveq #1,d2

.pn_positive:
    lea -16(a6),a1
    moveq #0,d3

    tst.l d1
    bne .pn_div_loop
    move.b #'0',(a1)+
    moveq #1,d3
    bra .pn_add_sign

.pn_div_loop:
    move.l d1,d4
    moveq #0,d6
    moveq #31,d7

; unsigned 32-bit divide by 10 via shift/subtract (X flag), quotient in d4, remainder in d6
.pn_div32:
    add.l d4,d4
    addx.l d6,d6
    cmp.l #10,d6
    blt .pn_div32_next
    sub.l #10,d6
    addq.l #1,d4

.pn_div32_next:
    dbra d7,.pn_div32

    move.b d6,d0
    add.b #'0',d0
    move.b d0,(a1)+
    addq.l #1,d3
    move.l d4,d1
    tst.l d1
    bne .pn_div_loop

.pn_add_sign:
    tst.b d2
    beq .pn_copy_rev
    move.b #'-',(a1)+
    addq.l #1,d3

.pn_copy_rev:
    lea dos_num_buffer,a0
    lea -16(a6),a1
    adda.l d3,a1
    move.l d3,d5

.pn_copy_loop:
    move.b -(a1),(a0)+
    subq.l #1,d5
    bgt .pn_copy_loop

    move.l dos_out_handle,d1
    lea dos_num_buffer,a0
    move.l a0,d2
    move.l dos_lib_base,a6
    jsr DOS_LVO_WRITE(a6)
    bra .pn_done

.pn_no_dos:
    moveq #-1,d0

.pn_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts
