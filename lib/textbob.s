; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; textbob.s
; Bake 8x8 font text into a chip planar BOB and return a CreateBob handle.
; Calling convention: link a6,#0 ; args at 8(a6), 12(a6), ...
; =============================================================================

    include "hardware.i"

    ifnd GFX_FONT_PLANES
GFX_FONT_PLANES      EQU 5
    endif
    ifnd GFX_SPACE_CODE
GFX_SPACE_CODE       EQU 32
    endif
    ifnd GFX_SPACE_GLYPH
GFX_SPACE_GLYPH      EQU 16
    endif

; PrintToBob flags
TB_FLAG_MASK         EQU 1       ; bit0: build cookie-cut mask
TB_FLAG_ADD_WORD     EQU 2       ; bit1: +16 px width for shifted PasteBob
TB_FLAG_OPAQUE       EQU 4       ; bit2: full 8x8 cell mask (opaque cell)

    XREF HeapAlloc
    XREF HeapFree
    XREF CreateBob
    XREF DestroyBob
    XREF gfx_current_mode
    XREF gfx_font_ptr

    SECTION textbob_code,CODE
    CNOP 0,4

; -----------------------------------------------------------------------------
; CreateTextBob(descriptor_ptr, save_background) -> handle | -1
; Alias for CreateBob (static DATA_C text assets use the same path).
; -----------------------------------------------------------------------------
    XDEF CreateTextBob
CreateTextBob:
    jmp CreateBob

; -----------------------------------------------------------------------------
; DestroyTextBob(handle) -> void
; Alias for DestroyBob (honours owns data/mask bit15).
; -----------------------------------------------------------------------------
    XDEF DestroyTextBob
DestroyTextBob:
    jmp DestroyBob

; Local geometry frame (after suba #24,sp), before descriptor push:
;   0(sp)  header_w.w
;   2(sp)  conv_w.w
;   4(sp)  planes.w
;   6(sp)  chunks.w
;   8(sp)  row_bytes_plane.w
;  10(sp)  bytes_per_image_row.w
;  12(sp)  payload_bytes.l
;  16(sp)  strlen.w
;  18(sp)  color.w
;  20(sp)  flags.w
;  22(sp)  pad.w

; -----------------------------------------------------------------------------
; PrintToBob(str_ptr, color, flags) -> handle | -1
; Renders a single-line NUL-terminated string into a heap chip BOB.
; Requires SetGraphicsMode (0/1/3) and SetFont beforehand.
; Flags: bit0=mask, bit1=add_word, bit2=opaque cell mask.
; On success the handle owns data/mask (DestroyBob frees them).
; -----------------------------------------------------------------------------
    XDEF PrintToBob
PrintToBob:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    moveq #0,d0
    move.l d0,a3                   ; a3 = data_ptr (cleanup)
    move.l d0,a4                   ; a4 = mask_ptr (cleanup)

    move.w gfx_current_mode,d0
    tst.w d0
    beq.s .ptb_mode_ok
    cmp.w #1,d0
    beq.s .ptb_mode_ok
    cmp.w #3,d0
    beq.s .ptb_mode_ok
    bra .ptb_fail
.ptb_mode_ok:
    move.l gfx_font_ptr,d0
    tst.l d0
    beq .ptb_fail

    move.l 8(a6),a0
    cmpa.l #0,a0
    beq .ptb_fail

    moveq #0,d7
.ptb_strlen:
    tst.b (a0)+
    beq.s .ptb_strlen_done
    addq.w #1,d7
    cmp.w #80,d7
    blt.s .ptb_strlen
.ptb_strlen_done:
    tst.w d7
    beq .ptb_fail

    move.w gfx_current_mode,d0
    tst.w d0
    beq.s .ptb_pl5
    cmp.w #1,d0
    beq.s .ptb_pl4
    moveq #3,d6
    bra.s .ptb_have_planes
.ptb_pl4:
    moveq #4,d6
    bra.s .ptb_have_planes
.ptb_pl5:
    moveq #5,d6
.ptb_have_planes:

    ; pixel_w = len * 8
    move.w d7,d1
    lsl.w #3,d1

    ; conv_w = max(16, round_up_16(pixel_w)); +16 if add_word
    move.w d1,d2
    addi.w #15,d2
    andi.w #$FFF0,d2
    cmp.w #16,d2
    bge.s .ptb_conv_ok
    move.w #16,d2
.ptb_conv_ok:
    move.l 16(a6),d0
    btst #1,d0
    beq.s .ptb_no_addw
    addi.w #16,d2
.ptb_no_addw:
    ; header_w = pixel_w (+16 if add_word)
    move.w d1,d3
    btst #1,d0
    beq.s .ptb_hdr_ok
    addi.w #16,d3
.ptb_hdr_ok:
    ; d2=conv_w d3=header_w d6=planes d7=len

    move.w d2,d4
    lsr.w #4,d4                    ; chunks
    move.w d4,d5
    add.w d5,d5                    ; row_bytes_plane

    suba.l #24,sp
    move.w d3,(sp)
    move.w d2,2(sp)
    move.w d6,4(sp)
    move.w d4,6(sp)
    move.w d5,8(sp)
    moveq #0,d1
    move.w d5,d1
    mulu d6,d1                     ; bytes_per_image_row
    move.w d1,10(sp)
    lsl.l #3,d1                    ; * height 8
    addq.l #4,d1
    move.l d1,12(sp)
    move.w d7,16(sp)
    move.l 12(a6),d1
    move.w d1,18(sp)
    move.l 16(a6),d1
    move.w d1,20(sp)
    clr.w 22(sp)

    ; Allocate data
    move.l 12(sp),d0
    addq.l #1,d0
    lsr.l #1,d0
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .ptb_fail_geom
    move.l d0,a3

    move.l a3,a0
    move.l 12(sp),d0
    lsr.l #1,d0
    subq.w #1,d0
.ptb_clr_data:
    clr.w (a0)+
    dbra d0,.ptb_clr_data

    move.w (sp),(a3)
    move.w #8,2(a3)

    ; Optional mask
    move.w 20(sp),d0
    btst #0,d0
    beq.s .ptb_no_mask_alloc
    move.l 12(sp),d0
    addq.l #1,d0
    lsr.l #1,d0
    move.l d0,-(sp)
    jsr HeapAlloc
    addq.l #4,sp
    tst.l d0
    beq .ptb_fail_geom
    move.l d0,a4

    move.l a4,a0
    move.l 12(sp),d0
    lsr.l #1,d0
    subq.w #1,d0
.ptb_clr_mask:
    clr.w (a0)+
    dbra d0,.ptb_clr_mask

    move.w (sp),(a4)
    move.w #8,2(a4)
.ptb_no_mask_alloc:

    ; Bake glyphs
    move.l 8(a6),a0
    moveq #0,d7
.ptb_char_loop:
    cmp.w 16(sp),d7
    bge .ptb_bake_done

    moveq #0,d0
    move.b (a0)+,d0
    cmpi.b #GFX_SPACE_CODE,d0
    bne.s .ptb_norm_ch
    moveq #GFX_SPACE_GLYPH,d1
    bra.s .ptb_idx_ok
.ptb_norm_ch:
    moveq #0,d1
    move.b d0,d1
    subi.w #32,d1
    bpl.s .ptb_idx_ok
    moveq #0,d1
.ptb_idx_ok:
    move.l gfx_font_ptr,a1
    move.l d1,d2
    lsl.l #3,d2
    moveq #GFX_FONT_PLANES,d0
    mulu d0,d2
    add.l d2,a1

    move.w d7,d1
    lsl.w #3,d1                    ; glyph pixel_x

    moveq #0,d5
.ptb_row_loop:
    move.b (a1,d5.w),d0            ; font byte

    move.w 4(sp),d6                ; planes
    moveq #0,d4
.ptb_plane_loop:
    move.w 18(sp),d2
    btst d4,d2
    beq.s .ptb_plane_next
    lea 4(a3),a2
    moveq #0,d2
    move.w 10(sp),d2
    mulu d5,d2
    add.l d2,a2
    moveq #0,d2
    move.w 8(sp),d2
    mulu d4,d2
    add.l d2,a2
    move.w d1,d2
    bsr .ptb_or_font_byte
.ptb_plane_next:
    addq.w #1,d4
    cmp.w d4,d6
    bgt.s .ptb_plane_loop

    cmpa.l #0,a4
    beq.s .ptb_row_next
    move.b (a1,d5.w),d0
    move.w 20(sp),d2
    btst #2,d2
    beq.s .ptb_mask_glyph
    move.b #$FF,d0
.ptb_mask_glyph:
    move.w 4(sp),d6
    moveq #0,d4
.ptb_mask_plane_loop:
    lea 4(a4),a2
    moveq #0,d2
    move.w 10(sp),d2
    mulu d5,d2
    add.l d2,a2
    moveq #0,d2
    move.w 8(sp),d2
    mulu d4,d2
    add.l d2,a2
    move.w d1,d2
    bsr .ptb_or_font_byte
    addq.w #1,d4
    cmp.w d4,d6
    bgt.s .ptb_mask_plane_loop

.ptb_row_next:
    addq.w #1,d5
    cmp.w #8,d5
    blt .ptb_row_loop

    addq.w #1,d7
    bra .ptb_char_loop

.ptb_bake_done:
    moveq #1,d0
    move.w 4(sp),d1
    lsl.w d1,d0                    ; color_count = 1 << planes

    suba.l #20,sp
    move.l a3,(sp)
    move.l a4,4(sp)
    clr.l 8(sp)
    move.w 22(sp),12(sp)           ; conv_w (geom at +20, field at +2)
    move.w #8,14(sp)
    move.w d0,16(sp)

    clr.l -(sp)
    lea 4(sp),a0
    move.l a0,-(sp)
    jsr CreateBob
    addq.l #8,sp
    adda.l #20,sp

    cmpi.l #-1,d0
    beq .ptb_fail_geom
    tst.l d0
    beq .ptb_fail_geom

    move.l d0,a0
    ori.w #$8000,16(a0)

    adda.l #24,sp
    ; d0 = handle (not in movem restore list)
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

.ptb_fail_geom:
    adda.l #24,sp
.ptb_fail:
    cmpa.l #0,a4
    beq.s .ptb_skip_free_mask
    move.l a4,-(sp)
    jsr HeapFree
    addq.l #4,sp
.ptb_skip_free_mask:
    cmpa.l #0,a3
    beq.s .ptb_skip_free_data
    move.l a3,-(sp)
    jsr HeapFree
    addq.l #4,sp
.ptb_skip_free_data:
    moveq #-1,d0
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts

; -----------------------------------------------------------------------------
; .ptb_or_font_byte
; OR font byte d0.b (MSB=left) into planar row a2 starting at pixel d2.w.
; Preserves d0/d1/d5-d7/a0-a6. Clobbers nothing visible after return.
; -----------------------------------------------------------------------------
.ptb_or_font_byte:
    movem.l d0-d4/a1,-(sp)
    move.w d2,a1                   ; a1.w = start pixel (use as word stash)
    moveq #0,d3
.ptb_ob_pix:
    moveq #7,d4
    sub.w d3,d4
    btst d4,d0
    beq.s .ptb_ob_next
    move.w a1,d2
    add.w d3,d2
    move.w d2,d4
    lsr.w #4,d4
    andi.w #15,d2
    moveq #15,d1
    sub.w d2,d1
    add.w d4,d4
    move.w (a2,d4.w),d2
    bset d1,d2
    move.w d2,(a2,d4.w)
.ptb_ob_next:
    addq.w #1,d3
    cmp.w #8,d3
    blt.s .ptb_ob_pix
    movem.l (sp)+,d0-d4/a1
    rts
