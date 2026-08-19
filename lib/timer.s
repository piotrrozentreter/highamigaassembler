; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; timer.s - bare-metal millisecond delay using the CIA-A Timer A (68000/OCS+)
; =============================================================================
; WaitMs busy-waits for a caller-specified number of milliseconds using CIA-A
; Timer A in one-shot mode, driven by the E-clock (not VBlank counting), so the
; delay is accurate regardless of the current display/DMA state.
;
; This codebase assumes a PAL (50 Hz) target (see WaitVBlank in helpers.s,
; which also hardcodes the PAL line count), so the PAL E-clock constant is
; used. CIA-A is used (never CIA-B, which lib/ptplayer.s owns for music
; playback) and CIACRA/CIAICR are always fully re-initialized before use, so
; WaitMs does not depend on - or disturb - any other CIA-A consumer's timer
; state (keyboard.s only uses the SP/serial interrupt, not Timer A).
;
; Known limitation: CIAICR is a shared "read clears all pending flags"
; register (Timer A/B, alarm, SP, FLAG all live in the same byte). A poll
; read here could in principle clear a keyboard SP-interrupt flag pending
; in the same bus cycle before the level-2 IRQ is serviced. The window is a
; single bus cycle within a multi-millisecond wait, so the risk is low, but
; genuinely time-critical CIA-A interrupt users should be aware of it.
; =============================================================================

    include "hardware.i"

ECLOCK_PAL_LO   EQU 54019       ; low word of the PAL E-clock, 709379 Hz
ECLOCK_PAL_HI   EQU 10          ; high word of the PAL E-clock (10<<16)+54019
CHUNK_MS_MAX    EQU 90          ; max ms per CIA one-shot load (16-bit timer)

    SECTION timer_code,CODE

    XDEF WaitMs

; -----------------------------------------------------------------------------
; Function: WaitMs
; Input: 8(a6)=ms (long, milliseconds to wait; <=0 returns immediately)
; Output: none
; Description: Busy-waits for the requested number of milliseconds using
;              CIA-A Timer A one-shot loads chained in <=90ms chunks.
; Notes: Interrupts are left enabled throughout (only CIA-A Timer A is
;        touched), so keyboard/other CIA-A interrupt users keep working.
; -----------------------------------------------------------------------------
WaitMs:
    link a6,#0
    movem.l d0-d3/a0,-(sp)
    move.l 8(a6),d3
    ble.s .done

    lea CIAA,a0

.chunk_loop:
    cmp.l #CHUNK_MS_MAX,d3
    bgt.s .full_chunk
    move.l d3,d2
    bra.s .compute
.full_chunk:
    move.l #CHUNK_MS_MAX,d2

.compute:
    ; d0 = d2(chunk ms, 0..90) * ECLOCK_PAL / 1000  (exact 32-bit multiply,
    ; then 32/16 divide; both fit since chunk ms is bounded to CHUNK_MS_MAX)
    move.w d2,d0
    mulu.w #ECLOCK_PAL_LO,d0
    move.w d2,d1
    mulu.w #ECLOCK_PAL_HI,d1
    swap d1
    add.l d1,d0
    divu.w #1000,d0
    and.l #$ffff,d0

    move.b #0,CIACRA(a0)
    move.b d0,CIATALO(a0)
    lsr.w #8,d0
    move.b d0,CIATAHI(a0)
    move.b #%00011001,CIACRA(a0)   ; LOAD+one-shot RUNMODE+START

.poll:
    move.b CIAICR(a0),d1
    btst #0,d1
    beq.s .poll

    sub.l d2,d3
    bgt.s .chunk_loop

.done:
    movem.l (sp)+,d0-d3/a0
    unlk a6
    rts
