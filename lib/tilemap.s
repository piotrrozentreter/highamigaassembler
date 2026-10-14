; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; tilemap.s
; Fast opaque tile blit for mode 0 (320x256 lores, 1..5 interleaved planes).
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
; Function: DrawTilemapLayer
; Input:  8(a6)=layer  12(a6)=tileset  16(a6)=tile_w  20(a6)=tile_h
;        24(a6)=planes  28(a6)=dest  32(a6)=dest_bpr
;        36(a6)=origin_x  40(a6)=origin_y  44(a6)=map_w  48(a6)=map_h
; Output: d0=0 ok, -1 error
; Description: Draw one layer; index 0 skips (no overwrite).
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
; Notes: Requires layers= directory. Use DrawTilemapMulti for different sheets.
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
