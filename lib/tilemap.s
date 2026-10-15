; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; tilemap.s
; Fast tile blit for mode 0 (320x256 lores, 1..5 interleaved planes).
; Opaque ($09F0) and colour-index-0 cookie-cut ($0FCA) paths.
; Mode 1 (640x256) is BOB-only — these routines refuse hires.
;
; Multi-layer map layout (from #import tilemap ... layers=):
;   map: DC.W w,h / DC.W layer_count / DC.W tile_w,tile_h / DC.L layer0..
;   layer: DC.W firstgid / DC.W indices... (1-based local; 0 = empty/skip)
;
; Calling convention: link a6,#0 ; long args at 8(a6), 12(a6), ...
; Requires a5 = CUSTOM ($DFF000), typically after TakeSystem().
; =============================================================================

    include "hardware.i"

    XREF gfx_current_mode

; Chip scratch: interleaved cookie mask for one tile (max 32x32x5 = 640 bytes).
TM_MASK_SCRATCH_BYTES = 640

WAITBLIT:MACRO
	tst.w DMACONR(a5)
	btst #6,DMACONR(a5)
	bne.s *-6
	ENDM

    SECTION tilemap_code,CODE
    CNOP 0,4

; ---------------------------------------------------------------------------
; _tm_blit_one
; In:  a0=tileset  a1=dest  d0.w=x  d1.w=y  d2.w=index0
;      d3.w=tile_w (16|32)  d4.w=tile_h  d5.w=planes  d6.w=dest_bpr
; Out: d0=0 ok / -1 fail. Preserves d3-d6. Scratch a0-a2,d0-d2,d7
; ---------------------------------------------------------------------------
_tm_blit_one:
    move.w d0,-(sp)
    cmp.w #16,d3
    beq.s .tb_w_ok
    cmp.w #32,d3
    bne .tb_fail
.tb_w_ok:
    and.w #15,d0
    bne .tb_fail

    move.w d3,d7
    lsr.w #3,d7
    move.w d4,d0
    mulu.w d5,d0
    mulu.w d7,d0
    mulu.w d2,d0
    adda.l d0,a0

    move.w d6,d0
    mulu.w d5,d0
    mulu.w d1,d0
    adda.l d0,a1
    move.w (sp),d0
    lsr.w #3,d0
    adda.w d0,a1

    move.w d3,d7
    lsr.w #4,d7
    move.w d7,d2
    add.w d2,d2
    move.w d6,d0
    sub.w d2,d0

    move.w d4,d1
    mulu.w d5,d1
    lsl.w #6,d1
    or.w d7,d1

    WAITBLIT
    move.l a0,BLTAPT(a5)
    move.l a1,BLTDPT(a5)
    move.w #$FFFF,BLTAFWM(a5)
    move.w #$FFFF,BLTALWM(a5)
    move.w #$09F0,BLTCON0(a5)
    move.w #0,BLTCON1(a5)
    move.w #0,BLTAMOD(a5)
    move.w d0,BLTDMOD(a5)
    move.w d1,BLTSIZE(a5)

    addq.l #2,sp
    moveq #0,d0
    rts
.tb_fail:
    addq.l #2,sp
    moveq #-1,d0
    rts


; ---------------------------------------------------------------------------
; _tm_blit_one_trans
; Colour-index-0 cookie-cut (same args / preserve rules as _tm_blit_one).
; Mask = OR of all planes for each pixel row, replicated `planes` times so the
; mask is row-interleaved like the tile. Blitter: A=mask B=src C=dst D=dst,
; minterm $0FCA (D = (A&B)|(~A&C)) — same channel layout as bob.s.
; Scratch fits max 32x32x5 in DATA_C. Scratch a0-a1,d0-d2,d7.
; a2/a3 preserved — DrawTilemapLayerTrans keeps tileset in a2 and layer
; cursor in a3 across blits (mask build temporarily uses both).
; ---------------------------------------------------------------------------
_tm_blit_one_trans:
    move.w d0,-(sp)
    cmp.w #16,d3
    beq.s .tt_w_ok
    cmp.w #32,d3
    bne .tt_fail
.tt_w_ok:
    and.w #15,d0
    bne .tt_fail
    tst.w d4
    beq .tt_fail
    tst.w d5
    beq .tt_fail
    cmp.w #5,d5
    bhi .tt_fail

    ; Reject tiles that would overflow the chip mask scratch.
    move.w d4,d0
    mulu.w d5,d0
    move.w d3,d7
    lsr.w #3,d7
    mulu.w d7,d0
    cmp.l #TM_MASK_SCRATCH_BYTES,d0
    bhi .tt_fail

    move.w d3,d7
    lsr.w #3,d7
    move.w d4,d0
    mulu.w d5,d0
    mulu.w d7,d0
    mulu.w d2,d0
    adda.l d0,a0

    move.w d6,d0
    mulu.w d5,d0
    mulu.w d1,d0
    adda.l d0,a1
    move.w (sp),d0
    lsr.w #3,d0
    adda.w d0,a1

    ; Previous cookie blit may still be DMA-reading _tm_mask_scratch — wait
    ; before rebuilding it or later tiles get a corrupted/empty mask.
    WAITBLIT

    ; ---- build interleaved cookie mask into _tm_mask_scratch ----
    ; a2 = mask out, a3 = plane walk; both restored for the layer loop.
    move.l a2,-(sp)
    move.l a3,-(sp)
    move.l a0,-(sp)                 ; save tile ptr for blit
    lea _tm_mask_scratch,a2
    move.w d4,d1
    subq.w #1,d1                    ; pixel-row dbf
    cmp.w #16,d3
    beq.s .tt_mask16

.tt_mask32_row:
    move.l a0,a3
    move.l (a3)+,d0
    move.w d5,d2
    subq.w #2,d2
    bmi.s .tt_mask32_rep            ; planes==1
.tt_mask32_or:
    or.l (a3)+,d0
    dbf d2,.tt_mask32_or
.tt_mask32_rep:
    move.l a3,a0                    ; next pixel row in tile
    move.w d5,d2
    subq.w #1,d2
.tt_mask32_dup:
    move.l d0,(a2)+
    dbf d2,.tt_mask32_dup
    dbf d1,.tt_mask32_row
    bra.s .tt_mask_done

.tt_mask16:
.tt_mask16_row:
    move.l a0,a3
    move.w (a3)+,d0
    move.w d5,d2
    subq.w #2,d2
    bmi.s .tt_mask16_rep
.tt_mask16_or:
    or.w (a3)+,d0
    dbf d2,.tt_mask16_or
.tt_mask16_rep:
    move.l a3,a0
    move.w d5,d2
    subq.w #1,d2
.tt_mask16_dup:
    move.w d0,(a2)+
    dbf d2,.tt_mask16_dup
    dbf d1,.tt_mask16_row

.tt_mask_done:
    move.l (sp)+,a0                 ; tile src
    move.l (sp)+,a3                 ; restore caller's a3
    ; caller's a2 still on stack; reuse a2 for BLTAPT then restore
    lea _tm_mask_scratch,a2         ; mask

    move.w d3,d7
    lsr.w #4,d7                     ; width words
    move.w d7,d2
    add.w d2,d2                     ; width bytes
    move.w d6,d0
    sub.w d2,d0                     ; C/D modulo

    move.w d4,d1
    mulu.w d5,d1
    lsl.w #6,d1
    or.w d7,d1                      ; BLTSIZE

    WAITBLIT
    move.l a2,BLTAPT(a5)            ; A = mask
    move.l a0,BLTBPT(a5)            ; B = tile src
    move.l a1,BLTCPT(a5)            ; C = dest
    move.l a1,BLTDPT(a5)            ; D = dest
    move.w #$FFFF,BLTAFWM(a5)
    move.w #$FFFF,BLTALWM(a5)
    move.w #$0FCA,BLTCON0(a5)       ; D = (A&B)|(~A&C)
    move.w #0,BLTCON1(a5)
    move.w #0,BLTAMOD(a5)
    move.w #0,BLTBMOD(a5)
    move.w d0,BLTCMOD(a5)
    move.w d0,BLTDMOD(a5)
    move.w d1,BLTSIZE(a5)

    move.l (sp)+,a2                 ; restore caller's a2 (tileset base)
    addq.l #2,sp
    moveq #0,d0
    rts
.tt_fail:
    addq.l #2,sp
    moveq #-1,d0
    rts


; -----------------------------------------------------------------------------
; Function: BlitTile
; Input:  8(a6)=tileset  12(a6)=index0  16(a6)=tile_w  20(a6)=tile_h
;        24(a6)=planes  28(a6)=dest  32(a6)=dest_bpr  36(a6)=x  40(a6)=y
; Output: d0=0 ok, -1 error
; Description: Opaque blitter copy of one planar tile (mode 0 only).
; -----------------------------------------------------------------------------
    XDEF BlitTile
BlitTile:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne.s .bt_fail

    move.l 8(a6),a0
    move.l 28(a6),a1
    move.l 36(a6),d0
    move.l 40(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    move.l 32(a6),d6
    bsr _tm_blit_one
    bra.s .bt_done
.bt_fail:
    moveq #-1,d0
.bt_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: BlitTileTrans
; Input:  same as BlitTile
; Output: d0=0 ok, -1 error
; Description: Cookie-cut blit; colour index 0 (all planes clear) is transparent.
; Notes: Builds an interleaved OR-mask in chip scratch (max 32x32x5).
; -----------------------------------------------------------------------------
    XDEF BlitTileTrans
BlitTileTrans:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne.s .btt_fail

    move.l 8(a6),a0
    move.l 28(a6),a1
    move.l 36(a6),d0
    move.l 40(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    move.l 32(a6),d6
    bsr _tm_blit_one_trans
    bra.s .btt_done
.btt_fail:
    moveq #-1,d0
.btt_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: DrawTilemapLayer
; Input:  8(a6)=layer  12(a6)=tileset  16(a6)=tile_w  20(a6)=tile_h
;        24(a6)=planes  28(a6)=dest  32(a6)=dest_bpr
;        36(a6)=origin_x  40(a6)=origin_y  44(a6)=map_w  48(a6)=map_h
; Output: d0=0 ok, -1 error
; Description: Opaque draw of one layer; index 0 skips (no overwrite).
; -----------------------------------------------------------------------------
    XDEF DrawTilemapLayer
DrawTilemapLayer:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne .dl_fail

    move.l 8(a6),a3
    addq.l #2,a3
    move.l 12(a6),a2
    move.l 28(a6),a4
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    move.l 32(a6),d6

    moveq #0,d7
.dl_y:
    cmp.l 48(a6),d7
    bge .dl_ok
    moveq #0,d1
.dl_x:
    cmp.l 44(a6),d1
    bge .dl_ynext

    move.w (a3)+,d2
    beq.s .dl_xnext
    subq.w #1,d2

    move.w d1,d0
    mulu.w d3,d0
    add.l 36(a6),d0
    move.l d1,-(sp)
    move.w d7,d1
    mulu.w d4,d1
    add.l 40(a6),d1

    move.l a2,a0
    move.l a4,a1
    move.l d7,-(sp)
    bsr _tm_blit_one
    move.l (sp)+,d7
    move.l (sp)+,d1
    tst.l d0
    bmi .dl_fail

.dl_xnext:
    addq.l #1,d1
    bra.s .dl_x

.dl_ynext:
    addq.l #1,d7
    bra.s .dl_y

.dl_ok:
    moveq #0,d0
    bra.s .dl_done
.dl_fail:
    moveq #-1,d0
.dl_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: DrawTilemapLayerTrans
; Input:  same as DrawTilemapLayer
; Output: d0=0 ok, -1 error
; Description: Cookie-cut layer draw; index 0 skips; colour-0 pixels transparent.
; Notes: Prefer for overlay layers (objects) over an opaque ground layer.
; -----------------------------------------------------------------------------
    XDEF DrawTilemapLayerTrans
DrawTilemapLayerTrans:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne .dlt_fail

    move.l 8(a6),a3
    addq.l #2,a3
    move.l 12(a6),a2
    move.l 28(a6),a4
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    move.l 32(a6),d6

    moveq #0,d7
.dlt_y:
    cmp.l 48(a6),d7
    bge .dlt_ok
    moveq #0,d1
.dlt_x:
    cmp.l 44(a6),d1
    bge .dlt_ynext

    move.w (a3)+,d2
    beq.s .dlt_xnext
    subq.w #1,d2

    move.w d1,d0
    mulu.w d3,d0
    add.l 36(a6),d0
    move.l d1,-(sp)
    move.w d7,d1
    mulu.w d4,d1
    add.l 40(a6),d1

    move.l a2,a0
    move.l a4,a1
    move.l d7,-(sp)
    bsr _tm_blit_one_trans
    move.l (sp)+,d7
    move.l (sp)+,d1
    tst.l d0
    bmi .dlt_fail

.dlt_xnext:
    addq.l #1,d1
    bra.s .dlt_x

.dlt_ynext:
    addq.l #1,d7
    bra.s .dlt_y

.dlt_ok:
    moveq #0,d0
    bra.s .dlt_done
.dlt_fail:
    moveq #-1,d0
.dlt_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: DrawTilemapGrid
; Input:  8(a6)=grid_ptr (single-layer: DC.W w,h + 0-based DC.W indices)
;        12(a6)=tileset  16(a6)=tile_w  20(a6)=tile_h  24(a6)=planes
;        28(a6)=dest  32(a6)=dest_bpr  36(a6)=origin_x  40(a6)=origin_y
; Output: d0=0 ok, -1 error
; Description: Draw a single-layer 0-based index grid (default #import tilemap).
; Notes: Index 0 is a real tileset tile. Multi-layer maps use DrawTilemap*.
; -----------------------------------------------------------------------------
    XDEF DrawTilemapGrid
DrawTilemapGrid:
    link a6,#0
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne .dg_fail

    move.l 8(a6),a3
    move.l 12(a6),a2
    move.l 28(a6),a4
    move.l 16(a6),d3
    move.l 20(a6),d4
    move.l 24(a6),d5
    move.l 32(a6),d6            ; dest_bpr stays in d6 for _tm_blit_one

    moveq #0,d0
    move.w (a3)+,d0             ; map_w
    move.l d0,-(sp)
    moveq #0,d1
    move.w (a3)+,d1             ; map_h
    move.l d1,-(sp)             ; (sp)=map_h, 4(sp)=map_w

    moveq #0,d7                 ; cell_y
.dg_y:
    cmp.l (sp),d7               ; map_h
    bge .dg_ok
    moveq #0,d1                 ; cell_x
.dg_x:
    cmp.l 4(sp),d1              ; map_w
    bge .dg_ynext

    move.w (a3)+,d2             ; 0-based — always blit
    move.w d1,d0
    mulu.w d3,d0
    add.l 36(a6),d0
    move.l d1,-(sp)
    move.w d7,d1
    mulu.w d4,d1
    add.l 40(a6),d1

    move.l a2,a0
    move.l a4,a1
    move.l d7,-(sp)
    bsr _tm_blit_one
    move.l (sp)+,d7
    move.l (sp)+,d1
    tst.l d0
    bmi .dg_fail_pop

    addq.l #1,d1
    bra.s .dg_x

.dg_ynext:
    addq.l #1,d7
    bra.s .dg_y

.dg_ok:
    lea 8(sp),sp
    moveq #0,d0
    bra.s .dg_done
.dg_fail_pop:
    lea 8(sp),sp
.dg_fail:
    moveq #-1,d0
.dg_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: DrawTilemap
; Input:  8(a6)=map_ptr  12(a6)=tileset  16(a6)=planes
;        20(a6)=dest  24(a6)=dest_bpr  28(a6)=origin_x  32(a6)=origin_y
; Output: d0=0 ok, -1 error
; Description: Draw all multi-layer layers bottom→top with one shared tileset.
; Notes: Opaque only. For overlays use DrawTilemapLayer + DrawTilemapLayerTrans.
;        Requires layers= directory. Use DrawTilemapMulti for different sheets.
; -----------------------------------------------------------------------------
    XDEF DrawTilemap
DrawTilemap:
    link a6,#-4
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne .dt_fail

    move.l 8(a6),a2
    move.w 4(a2),d5
    lea 10(a2),a4
    move.w d5,-2(a6)
    clr.w -4(a6)

.dt_loop:
    move.w -4(a6),d7
    cmp.w -2(a6),d7
    bge .dt_ok

    moveq #0,d0
    move.w d7,d0
    lsl.l #2,d0
    move.l 0(a4,d0.l),a3

    moveq #0,d0
    move.w 2(a2),d0
    move.l d0,-(sp)
    moveq #0,d0
    move.w (a2),d0
    move.l d0,-(sp)
    move.l 32(a6),-(sp)
    move.l 28(a6),-(sp)
    move.l 24(a6),-(sp)
    move.l 20(a6),-(sp)
    move.l 16(a6),-(sp)
    moveq #0,d0
    move.w 8(a2),d0
    move.l d0,-(sp)
    moveq #0,d0
    move.w 6(a2),d0
    move.l d0,-(sp)
    move.l 12(a6),-(sp)
    move.l a3,-(sp)
    jsr DrawTilemapLayer
    lea 44(sp),sp
    tst.l d0
    bmi .dt_fail

    addq.w #1,-4(a6)
    bra .dt_loop

.dt_ok:
    moveq #0,d0
    bra.s .dt_done
.dt_fail:
    moveq #-1,d0
.dt_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; -----------------------------------------------------------------------------
; Function: DrawTilemapMulti
; Input:  8(a6)=map_ptr  12(a6)=tileset_table (DC.L per layer)
;        16(a6)=planes  20(a6)=dest  24(a6)=dest_bpr
;        28(a6)=origin_x  32(a6)=origin_y
; Output: d0=0 ok, -1 error
; Description: Draw all layers; tileset_table[i] used for layer i.
; Notes: Opaque only. Mix DrawTilemapLayer / DrawTilemapLayerTrans per layer
;        when ground must be opaque and objects colour-0 transparent.
; -----------------------------------------------------------------------------
    XDEF DrawTilemapMulti
DrawTilemapMulti:
    link a6,#-4
    movem.l d1-d7/a0-a4,-(sp)

    move.w gfx_current_mode,d0
    bne .dm_fail

    move.l 8(a6),a2
    move.l 12(a6),a1
    move.w 4(a2),d5
    lea 10(a2),a4
    move.w d5,-2(a6)
    clr.w -4(a6)

.dm_loop:
    move.w -4(a6),d7
    cmp.w -2(a6),d7
    bge .dm_ok

    moveq #0,d0
    move.w d7,d0
    lsl.l #2,d0
    move.l 0(a4,d0.l),a3
    move.l 0(a1,d0.l),a0
    move.l a1,-(sp)

    moveq #0,d1
    move.w 2(a2),d1
    move.l d1,-(sp)
    moveq #0,d1
    move.w (a2),d1
    move.l d1,-(sp)
    move.l 32(a6),-(sp)
    move.l 28(a6),-(sp)
    move.l 24(a6),-(sp)
    move.l 20(a6),-(sp)
    move.l 16(a6),-(sp)
    moveq #0,d1
    move.w 8(a2),d1
    move.l d1,-(sp)
    moveq #0,d1
    move.w 6(a2),d1
    move.l d1,-(sp)
    move.l a0,-(sp)
    move.l a3,-(sp)
    jsr DrawTilemapLayer
    lea 44(sp),sp
    move.l (sp)+,a1
    tst.l d0
    bmi .dm_fail

    addq.w #1,-4(a6)
    bra .dm_loop

.dm_ok:
    moveq #0,d0
    bra.s .dm_done
.dm_fail:
    moveq #-1,d0
.dm_done:
    movem.l (sp)+,d1-d7/a0-a4
    unlk a6
    rts


; ---------------------------------------------------------------------------
; Chip RAM scratch for one interleaved cookie mask (max tile 32x32, 5 planes).
; ---------------------------------------------------------------------------
    SECTION tilemap_chip,DATA_C
    CNOP 0,4
_tm_mask_scratch:
    DS.B TM_MASK_SCRATCH_BYTES
