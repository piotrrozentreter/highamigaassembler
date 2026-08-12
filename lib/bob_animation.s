; =============================================================================
; bob_animation.s
; Frame-sequence animation for BOB descriptors
; Calling convention: link a6,#0 ; args at 8(a6), 12(a6), ...
; =============================================================================

    XREF HeapAlloc
    XREF HeapFree
    XREF CreateBob
    XREF DestroyBob

    XDEF CreateBobAnimation
    XDEF AddBobAnimationFrame
    XDEF PlayBobAnimation
    XDEF StopBobAnimation
    XDEF AnimateBob
    XDEF DestroyBobAnimation

ANIM_HEAD           EQU 0
ANIM_TAIL           EQU 4
ANIM_CURRENT        EQU 8
ANIM_REMAINING      EQU 12
ANIM_FLAGS          EQU 14
ANIM_SAVE_BG        EQU 16
ANIM_SIZE           EQU 20

FRAME_NEXT          EQU 0
FRAME_BOB           EQU 4
FRAME_DELAY         EQU 8
FRAME_SIZE          EQU 12

ANIM_PLAYING        EQU 0
ANIM_LOOPING        EQU 1

    SECTION bob_animation_code,CODE

; -----------------------------------------------------------------------------
; Function: CreateBobAnimation
; Input: 8(a6)=descriptor, 12(a6)=delay, 16(a6)=save_background
; Output: d0=animation handle or -1
; Description: Creates an animation containing its first BOB frame.
; Notes: The animation starts stopped and owns the created BOB handle.
; -----------------------------------------------------------------------------
CreateBobAnimation:
    link a6,#0
    movem.l d1-d3/a0-a4,-(sp)

    move.l #ANIM_SIZE/2,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .cba_fail
    move.l d0,a2

    clr.l ANIM_HEAD(a2)
    clr.l ANIM_TAIL(a2)
    clr.l ANIM_CURRENT(a2)
    clr.w ANIM_REMAINING(a2)
    clr.w ANIM_FLAGS(a2)
    move.w 18(a6),ANIM_SAVE_BG(a2)
    clr.w 18(a2)

    move.l 16(a6),-(sp)
    move.l 8(a6),-(sp)
    jsr CreateBob
    addq.l #8,sp
    cmp.l #-1,d0
    beq .cba_free_animation
    move.l d0,a3

    move.l #FRAME_SIZE/2,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .cba_free_bob
    move.l d0,a4

    clr.l FRAME_NEXT(a4)
    move.l a3,FRAME_BOB(a4)
    move.l 12(a6),d1
    bsr BobAnimationNormalizeDelay
    move.w d1,FRAME_DELAY(a4)

    move.l a4,ANIM_HEAD(a2)
    move.l a4,ANIM_TAIL(a2)
    move.l a4,ANIM_CURRENT(a2)
    move.w d1,ANIM_REMAINING(a2)
    move.l a2,d0
    bra .cba_done

.cba_free_bob:
    move.l a3,-(sp)
    jsr DestroyBob
    addq.l #4,sp
.cba_free_animation:
    move.l a2,-(sp)
    jsr HeapFree
    addq.l #4,sp
.cba_fail:
    moveq #-1,d0
.cba_done:
    movem.l (sp)+,d1-d3/a0-a4
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: AddBobAnimationFrame
; Input: 8(a6)=animation, 12(a6)=descriptor, 16(a6)=delay
; Output: d0=0 on success or -1
; Description: Appends a BOB descriptor to an animation sequence.
; Notes: Uses the background-save policy selected at animation creation.
; -----------------------------------------------------------------------------
AddBobAnimationFrame:
    link a6,#0
    movem.l d1-d3/a0-a4,-(sp)

    move.l 8(a6),a2
    cmpa.l #0,a2
    beq .abaf_fail
    cmpa.l #-1,a2
    beq .abaf_fail

    moveq #0,d0
    move.w ANIM_SAVE_BG(a2),d0
    move.l d0,-(sp)
    move.l 12(a6),-(sp)
    jsr CreateBob
    addq.l #8,sp
    cmp.l #-1,d0
    beq .abaf_fail
    move.l d0,a3

    move.l #FRAME_SIZE/2,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .abaf_free_bob
    move.l d0,a4

    clr.l FRAME_NEXT(a4)
    move.l a3,FRAME_BOB(a4)
    move.l 16(a6),d1
    bsr BobAnimationNormalizeDelay
    move.w d1,FRAME_DELAY(a4)

    move.l ANIM_TAIL(a2),a0
    move.l a4,FRAME_NEXT(a0)
    move.l a4,ANIM_TAIL(a2)
    moveq #0,d0
    bra .abaf_done

.abaf_free_bob:
    move.l a3,-(sp)
    jsr DestroyBob
    addq.l #4,sp
.abaf_fail:
    moveq #-1,d0
.abaf_done:
    movem.l (sp)+,d1-d3/a0-a4
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PlayBobAnimation
; Input: 8(a6)=animation, 12(a6)=mode (0=once, non-zero=loop)
; Output: d0=0 on success or -1
; Description: Rewinds the sequence and starts playback.
; Notes: Play-once mode freezes on the final frame.
; -----------------------------------------------------------------------------
PlayBobAnimation:
    link a6,#0
    movem.l d1/a0-a1,-(sp)
    move.l 8(a6),a0
    cmpa.l #0,a0
    beq .pba_fail
    cmpa.l #-1,a0
    beq .pba_fail

    move.l ANIM_HEAD(a0),a1
    cmpa.l #0,a1
    beq .pba_fail
    move.l a1,ANIM_CURRENT(a0)
    move.w FRAME_DELAY(a1),ANIM_REMAINING(a0)
    move.w #1,ANIM_FLAGS(a0)
    tst.l 12(a6)
    beq .pba_ok
    ori.w #2,ANIM_FLAGS(a0)
.pba_ok:
    moveq #0,d0
    bra .pba_done
.pba_fail:
    moveq #-1,d0
.pba_done:
    movem.l (sp)+,d1/a0-a1
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: StopBobAnimation
; Input: 8(a6)=animation
; Output: none
; Description: Stops playback without changing the current frame.
; Notes: Null and -1 handles are ignored.
; -----------------------------------------------------------------------------
StopBobAnimation:
    link a6,#0
    move.l a0,-(sp)
    move.l 8(a6),a0
    cmpa.l #0,a0
    beq .sba_done
    cmpa.l #-1,a0
    beq .sba_done
    andi.w #$FFFE,ANIM_FLAGS(a0)
.sba_done:
    move.l (sp)+,a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: AnimateBob
; Input: 8(a6)=animation
; Output: d0=current BOB handle or -1
; Description: Advances one game tick and returns the frame to draw.
; Notes: Pass the returned handle to PasteBob; delays count AnimateBob calls.
; -----------------------------------------------------------------------------
AnimateBob:
    link a6,#0
    movem.l d1/a0-a2,-(sp)
    move.l 8(a6),a0
    cmpa.l #0,a0
    beq .ab_fail
    cmpa.l #-1,a0
    beq .ab_fail
    move.l ANIM_CURRENT(a0),a1
    cmpa.l #0,a1
    beq .ab_fail

    move.l FRAME_BOB(a1),d0
    move.w ANIM_FLAGS(a0),d1
    btst #ANIM_PLAYING,d1
    beq .ab_done
    subq.w #1,ANIM_REMAINING(a0)
    bne .ab_done

    move.l FRAME_NEXT(a1),a2
    cmpa.l #0,a2
    bne .ab_select_frame
    btst #ANIM_LOOPING,d1
    beq .ab_stop_last
    move.l ANIM_HEAD(a0),a2
.ab_select_frame:
    move.l a2,ANIM_CURRENT(a0)
    move.w FRAME_DELAY(a2),ANIM_REMAINING(a0)
    bra .ab_done

.ab_stop_last:
    andi.w #$FFFE,ANIM_FLAGS(a0)
    move.w #1,ANIM_REMAINING(a0)
    bra .ab_done
.ab_fail:
    moveq #-1,d0
.ab_done:
    movem.l (sp)+,d1/a0-a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: DestroyBobAnimation
; Input: 8(a6)=animation
; Output: none
; Description: Destroys every frame BOB, list node, and the animation object.
; Notes: Null and -1 handles are ignored.
; -----------------------------------------------------------------------------
DestroyBobAnimation:
    link a6,#0
    movem.l d0/a0-a4,-(sp)
    move.l 8(a6),a2
    cmpa.l #0,a2
    beq .dba_done
    cmpa.l #-1,a2
    beq .dba_done
    move.l ANIM_HEAD(a2),a3
.dba_loop:
    cmpa.l #0,a3
    beq .dba_free_animation
    move.l FRAME_NEXT(a3),a4
    move.l FRAME_BOB(a3),-(sp)
    jsr DestroyBob
    addq.l #4,sp
    move.l a3,-(sp)
    jsr HeapFree
    addq.l #4,sp
    move.l a4,a3
    bra .dba_loop
.dba_free_animation:
    move.l a2,-(sp)
    jsr HeapFree
    addq.l #4,sp
.dba_done:
    movem.l (sp)+,d0/a0-a4
    unlk a6
    rts

; Clamp frame delays to the unsigned word range, with zero meaning one tick.
BobAnimationNormalizeDelay:
    cmp.l #1,d1
    bge .nd_check_max
    moveq #1,d1
    rts
.nd_check_max:
    cmp.l #65535,d1
    ble .nd_done
    move.l #65535,d1
.nd_done:
    rts