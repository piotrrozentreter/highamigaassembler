; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; gui_intuition.s - System-friendly Intuition GUI runtime for HAS (M68000)
;
; Implements the contract defined in docs/GUI_INTUITION_RUNTIME_SPEC.md so that
; forms produced by guicreator/ can open a real intuition.library window with
; buttons, string gadgets and static labels.
;
; Design:
; - System-friendly only. No $DFF0xx access, no TakeSystem(). Everything is
;   rendered through the window's RastPort via PrintIText / the gadget Border
;   imagery that Intuition draws itself.
; - Own cached intuition.library / graphics.library bases (existing convention:
;   every lib module caches its own bases).
; - Static pools only: no AllocMem, no failure path, no leak. GuiAdd* returns
;   -1 when a pool is exhausted.
; - All storage lives in plain fast RAM (DATA/BSS). Nothing here is DMA'd by
;   the custom chips, so DATA_C/BSS_C must never be used.
;
; Calling convention:
; - HAS pushes arguments right-to-left as 32-bit longs and cleans the stack
;   itself, so after "link a6,#0" the FIRST declared parameter is at 8(a6),
;   the second at 12(a6), and so on. Results are returned in d0.
; - Each routine copies a6 into a5 immediately after the link so that a6 is
;   free to hold library bases while parameters remain reachable at 8(a5)...
; - movem.l restores a6 with the frame pointer value before "unlk a6", exactly
;   as lib/dos.s does.
;
; Public API (see spec section 1):
;   GuiInit() -> int                     ; 0 ok, -1 fail (idempotent)
;   GuiShutdown() -> void
;   GuiBeginWindow(title,x,y,w,h,idcmp,flags) -> int   ; 0 ok, -1 busy
;   GuiAddLabel(id,x,y,text) -> int
;   GuiAddButton(id,x,y,w,h,caption) -> int
;   GuiAddEditBox(id,x,y,w,h,buf,undo,maxlen) -> int
;   GuiAddCheckBox(id,x,y,w,h,caption,checked) -> int
;   GuiAddList(id,x,y,w,h,labels,count,selected) -> int
;   GuiAddBitmap(id,x,y,w,h,image) -> int
;   GuiShow() -> int                     ; Window*, 0 fail, -1 order violation
;   GuiCloseWindow() -> void
;   GuiWaitEvent() -> int                ; GUI_EVT_*, -1 if not shown
;   GuiGetEventID() / GuiGetEventCode() / GuiGetEventX() / GuiGetEventY()
;   GuiGetEditText(id) -> int
;   GuiSetEditText(id,text) -> int
;   GuiSetLabelText(id,text) -> int
;   GuiEnableWidget(id,enable) -> int
;   GuiActivateEdit(id) -> int
;   GuiRedraw() -> void
; =============================================================================

    include "hardware.i"
    include "exec_lib.i"
    include "graphics_lib.i"
    include "gui_intuition.i"

; =============================================================================
; Initialised module state
; =============================================================================

    SECTION gui_intuition_data,DATA

gui_int_name:
    dc.b "intuition.library",0
    even
gui_gfx_name:
    dc.b "graphics.library",0
    even

gui_int_base:
    dc.l 0                          ; IntuitionBase
gui_gfx_base:
    dc.l 0                          ; GfxBase
gui_window:
    dc.l 0                          ; struct Window *, 0 = closed
gui_rport:
    dc.l 0                          ; Window->RPort    (WD_RPORT)
gui_userport:
    dc.l 0                          ; Window->UserPort (WD_USERPORT)
gui_sigmask:
    dc.l 0                          ; 1 << UserPort->mp_SigBit
gui_firstgad:
    dc.l 0                          ; head of the built gadget list
gui_lastgad:
    dc.l 0                          ; tail, for O(1) append
gui_building:
    dc.w 0                          ; 1 between GuiBeginWindow and GuiShow
gui_shown:
    dc.w 0                          ; 1 once OpenWindow succeeded
gui_ngads:
    dc.w 0
gui_nlabels:
    dc.w 0
gui_evt_id:
    dc.l 0
gui_evt_code:
    dc.l 0
gui_evt_mx:
    dc.w 0
gui_evt_my:
    dc.w 0

; =============================================================================
; Static pools (spec 4.4) - plain fast RAM, never chip RAM
; =============================================================================

    SECTION gui_intuition_bss,BSS

gui_nw:
    ds.b NW_SIZEOF
gui_gadgets:
    ds.b GG_SIZEOF*GUI_MAX_GADGETS
gui_borders:
    ds.b BD_SIZEOF*GUI_MAX_GADGETS*2
gui_bordxy:
    ds.w 12*GUI_MAX_GADGETS
gui_itexts:
    ds.b IT_SIZEOF*GUI_MAX_GADGETS
gui_strinfo:
    ds.b SI_SIZEOF*GUI_MAX_GADGETS
gui_labels:
    ds.b IT_SIZEOF*GUI_MAX_LABELS
gui_label_xy:
    ds.w 2*GUI_MAX_LABELS
gui_label_id:
    ds.w GUI_MAX_LABELS
gui_widget_kind:
    ds.w GUI_MAX_GADGETS
gui_list_labels:
    ds.l GUI_MAX_GADGETS
gui_list_count:
    ds.w GUI_MAX_GADGETS
gui_list_selected:
    ds.w GUI_MAX_GADGETS

; =============================================================================
; Code
; =============================================================================

    SECTION gui_intuition_code,CODE

    XDEF GuiInit
    XDEF GuiShutdown
    XDEF GuiBeginWindow
    XDEF GuiAddLabel
    XDEF GuiAddButton
    XDEF GuiAddEditBox
    XDEF GuiAddCheckBox
    XDEF GuiAddList
    XDEF GuiAddBitmap
    XDEF GuiShow
    XDEF GuiCloseWindow
    XDEF GuiWaitEvent
    XDEF GuiGetEventID
    XDEF GuiGetEventCode
    XDEF GuiGetEventX
    XDEF GuiGetEventY
    XDEF GuiGetCheckBox
    XDEF GuiGetListSelected
    XDEF GuiGetEditText
    XDEF GuiSetEditText
    XDEF GuiSetLabelText
    XDEF GuiEnableWidget
    XDEF GuiActivateEdit
    XDEF GuiRedraw

; -----------------------------------------------------------------------------
; Function: GuiInit
; Input: none
; Output: d0=0 success, d0=-1 failure
; Description: Opens intuition.library V37 and graphics.library V37 and caches
;              both bases. If graphics fails, intuition is closed again.
; Notes: Idempotent; a second successful call is a no-op.
; -----------------------------------------------------------------------------
GuiInit:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)

    move.l gui_int_base,d0
    beq .gi_open
    move.l gui_gfx_base,d0
    bne .gi_ok

.gi_open:
    move.l ExecBase,a6

    move.l gui_int_base,d0
    bne .gi_have_int
    lea gui_int_name,a1
    moveq #GUI_LIB_VERSION,d0
    jsr _LVOOpenLibrary(a6)
    move.l d0,gui_int_base
    beq .gi_fail

.gi_have_int:
    lea gui_gfx_name,a1
    moveq #GUI_LIB_VERSION,d0
    jsr _LVOOpenLibrary(a6)
    move.l d0,gui_gfx_base
    bne .gi_ok

    move.l gui_int_base,d0
    beq .gi_fail
    move.l d0,a1
    jsr _LVOCloseLibrary(a6)
    clr.l gui_int_base
    bra .gi_fail

.gi_ok:
    moveq #0,d0
    bra .gi_done

.gi_fail:
    moveq #-1,d0

.gi_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiShutdown
; Input: none
; Output: none (d0 undefined)
; Description: Closes the window if it is still open, then graphics.library and
;              intuition.library, in reverse open order (gotcha 4).
; Notes: Idempotent.
; -----------------------------------------------------------------------------
GuiShutdown:
    link a6,#0
    movem.l d0-d7/a0-a6,-(sp)

    bsr gui_do_close_window

    move.l ExecBase,a6

    move.l gui_gfx_base,d0
    beq .gs_no_gfx
    move.l d0,a1
    jsr _LVOCloseLibrary(a6)
    clr.l gui_gfx_base

.gs_no_gfx:
    move.l gui_int_base,d0
    beq .gs_no_int
    move.l d0,a1
    jsr _LVOCloseLibrary(a6)
    clr.l gui_int_base

.gs_no_int:
    movem.l (sp)+,d0-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiBeginWindow
; Input: 8(a6)=title, 12(a6)=x, 16(a6)=y, 20(a6)=w, 24(a6)=h,
;        28(a6)=idcmp, 32(a6)=flags
; Output: d0=0 success, d0=-1 if a window is already open
; Description: Fills the private NewWindow template and resets the widget
;              pools. Opens nothing yet.
; Notes: nw_Screen/nw_BitMap are 0 (Workbench screen). GIMMEZEROZERO is not
;        used, so the caller's coordinates are already window-relative.
; -----------------------------------------------------------------------------
GuiBeginWindow:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    tst.w gui_shown
    bne .gbw_fail
    move.l gui_window,d0
    bne .gbw_fail

    ; reset the build state; re-terminate the list explicitly (gotcha 5)
    clr.w gui_ngads
    clr.w gui_nlabels
    clr.l gui_firstgad
    clr.l gui_lastgad
    clr.l gui_evt_id
    clr.l gui_evt_code
    clr.w gui_evt_mx
    clr.w gui_evt_my

    lea gui_nw,a0

    move.l 12(a5),d0
    move.w d0,NW_LEFTEDGE(a0)
    move.l 16(a5),d0
    move.w d0,NW_TOPEDGE(a0)
    move.l 20(a5),d0
    move.w d0,NW_WIDTH(a0)
    move.l 24(a5),d0
    move.w d0,NW_HEIGHT(a0)

    move.b #$FF,NW_DETAILPEN(a0)
    move.b #$FF,NW_BLOCKPEN(a0)

    move.l 28(a5),NW_IDCMPFLAGS(a0)
    move.l 32(a5),NW_FLAGS(a0)

    clr.l NW_FIRSTGADGET(a0)
    clr.l NW_CHECKMARK(a0)
    move.l 8(a5),NW_TITLE(a0)
    clr.l NW_SCREEN(a0)
    clr.l NW_BITMAP(a0)

    move.w #GUI_MIN_WIDTH,NW_MINWIDTH(a0)
    move.w #GUI_MIN_HEIGHT,NW_MINHEIGHT(a0)
    move.w #$FFFF,NW_MAXWIDTH(a0)
    move.w #$FFFF,NW_MAXHEIGHT(a0)
    move.w #WBENCHSCREEN,NW_TYPE(a0)

    move.w #1,gui_building
    moveq #0,d0
    bra .gbw_done

.gbw_fail:
    moveq #-1,d0

.gbw_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiAddLabel
; Input: 8(a6)=id, 12(a6)=x, 16(a6)=y, 20(a6)=text
; Output: d0=0 success, d0=-1 on order violation or exhausted pool
; Description: Registers a static IntuiText plus its draw offsets. Labels are
;              not gadgets and produce no events; they are painted by GuiShow
;              and repainted on every IDCMP_REFRESHWINDOW.
; Notes: Uses JAM2 so that GuiSetLabelText() overwrites the old glyphs.
; -----------------------------------------------------------------------------
GuiAddLabel:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    tst.w gui_building
    beq .gal_fail
    tst.w gui_shown
    bne .gal_fail

    move.w gui_nlabels,d7
    cmp.w #GUI_MAX_LABELS,d7
    bge .gal_fail

    ; a0 = &gui_labels[n]
    move.w d7,d0
    mulu.w #IT_SIZEOF,d0
    lea gui_labels,a0
    add.l d0,a0

    move.b #1,IT_FRONTPEN(a0)
    clr.b IT_BACKPEN(a0)
    move.b #JAM2,IT_DRAWMODE(a0)
    clr.b IT_PAD(a0)
    clr.w IT_LEFTEDGE(a0)
    clr.w IT_TOPEDGE(a0)
    clr.l IT_ITEXTFONT(a0)
    move.l 20(a5),IT_ITEXT(a0)
    clr.l IT_NEXTTEXT(a0)

    ; a1 = &gui_label_xy[n]
    move.w d7,d0
    mulu.w #4,d0
    lea gui_label_xy,a1
    add.l d0,a1
    move.l 12(a5),d0
    move.w d0,(a1)
    move.l 16(a5),d0
    move.w d0,2(a1)

    ; a2 = &gui_label_id[n]
    move.w d7,d0
    add.w d0,d0
    lea gui_label_id,a2
    adda.w d0,a2
    move.l 8(a5),d0
    move.w d0,(a2)

    addq.w #1,gui_nlabels
    moveq #0,d0
    bra .gal_done

.gal_fail:
    moveq #-1,d0

.gal_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiAddButton
; Input: 8(a6)=id, 12(a6)=x, 16(a6)=y, 20(a6)=w, 24(a6)=h, 28(a6)=caption
; Output: d0=0 success, d0=-1 on order violation or exhausted pool
; Description: Appends a GTYP_BOOLGADGET with an auto-generated 5-point Border
;              box and a centred IntuiText caption (spec 4.1).
; Notes: The Border polyline is NOT auto-closed, hence the repeated 0,0 point.
;        Caption centring assumes the 8x8 topaz font.
; -----------------------------------------------------------------------------
GuiAddButton:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    tst.w gui_building
    beq .gab_fail
    tst.w gui_shown
    bne .gab_fail

    move.w gui_ngads,d7
    cmp.w #GUI_MAX_GADGETS,d7
    bge .gab_fail

    bsr gui_slot_ptrs               ; d7 -> a0=gad a1=bord1 a2=xy1 a3=itext a4=si
    lea BD_SIZEOF(a1),a6            ; a6 = bord2
    lea 12(a2),a4                   ; a4 = xy2

    move.l 20(a5),d4                ; d4 = w
    move.l 24(a5),d5                ; d5 = h

    ; ---- Gadget ----
    clr.l GG_NEXTGADGET(a0)
    move.l 12(a5),d0
    move.w d0,GG_LEFTEDGE(a0)
    move.l 16(a5),d0
    move.w d0,GG_TOPEDGE(a0)
    move.w d4,GG_WIDTH(a0)
    move.w d5,GG_HEIGHT(a0)
    move.w #GFLG_GADGHCOMP,GG_FLAGS(a0)
    move.w #GACT_RELVERIFY,GG_ACTIVATION(a0)
    move.w #GTYP_BOOLGADGET,GG_GADGETTYPE(a0)
    move.l a1,GG_GADGETRENDER(a0)
    clr.l GG_SELECTRENDER(a0)
    move.l a3,GG_GADGETTEXT(a0)
    clr.l GG_MUTUALEXCLUDE(a0)
    clr.l GG_SPECIALINFO(a0)
    move.l 8(a5),d0
    move.w d0,GG_GADGETID(a0)
    clr.l GG_USERDATA(a0)

    ; ---- Border 1 (Top and Left: Pen 2 White highlight) ----
    clr.w BD_LEFTEDGE(a1)
    clr.w BD_TOPEDGE(a1)
    move.b #2,BD_FRONTPEN(a1)
    clr.b BD_BACKPEN(a1)
    move.b #JAM1,BD_DRAWMODE(a1)
    move.b #3,BD_COUNT(a1)
    move.l a2,BD_XY(a1)
    move.l a6,BD_NEXTBORDER(a1)

    ; ---- Border 1 polyline: (0, h-2) -> (0, 0) -> (w-2, 0) ----
    move.w d4,d2
    subq.w #2,d2                    ; d2 = w-2
    move.w d5,d3
    subq.w #2,d3                    ; d3 = h-2
    clr.w 0(a2)
    move.w d3,2(a2)
    clr.w 4(a2)
    clr.w 6(a2)
    move.w d2,8(a2)
    clr.w 10(a2)

    ; ---- Border 2 (Bottom and Right: Pen 1 Black shadow) ----
    clr.w BD_LEFTEDGE(a6)
    clr.w BD_TOPEDGE(a6)
    move.b #1,BD_FRONTPEN(a6)
    clr.b BD_BACKPEN(a6)
    move.b #JAM1,BD_DRAWMODE(a6)
    move.b #3,BD_COUNT(a6)
    move.l a4,BD_XY(a6)
    clr.l BD_NEXTBORDER(a6)

    ; ---- Border 2 polyline: (w-1, 0) -> (w-1, h-1) -> (0, h-1) ----
    move.w d4,d2
    subq.w #1,d2                    ; d2 = w-1
    move.w d5,d3
    subq.w #1,d3                    ; d3 = h-1
    move.w d2,0(a4)
    clr.w 2(a4)
    move.w d2,4(a4)
    move.w d3,6(a4)
    clr.w 8(a4)
    move.w d3,10(a4)

    ; ---- IntuiText caption, centred ----
    move.b #1,IT_FRONTPEN(a3)
    clr.b IT_BACKPEN(a3)
    move.b #JAM1,IT_DRAWMODE(a3)
    clr.b IT_PAD(a3)
    clr.l IT_ITEXTFONT(a3)
    move.l 28(a5),IT_ITEXT(a3)
    clr.l IT_NEXTTEXT(a3)

    move.l 28(a5),d0
    bsr gui_strlen                  ; d0 = length in characters
    mulu.w #GUI_FONT_WIDTH,d0
    move.w d4,d1
    sub.w d0,d1
    asr.w #1,d1
    move.w d1,IT_LEFTEDGE(a3)
    move.w d5,d1
    sub.w #GUI_FONT_HEIGHT,d1
    asr.w #1,d1
    move.w d1,IT_TOPEDGE(a3)

    ; the StringInfo slot of this index stays unused for bool gadgets

    ; gui_strlen (above) clobbered a0; reload the gadget pointer before linking.
    move.w d7,d0
    mulu.w #GG_SIZEOF,d0
    lea gui_gadgets,a0
    add.l d0,a0
    bsr gui_link_gadget             ; a0 = gadget to append
    addq.w #1,gui_ngads
    moveq #0,d0
    bra .gab_done

.gab_fail:
    moveq #-1,d0

.gab_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiAddEditBox
; Input: 8(a6)=id, 12(a6)=x, 16(a6)=y, 20(a6)=w, 24(a6)=h,
;        28(a6)=buf, 32(a6)=undo, 36(a6)=maxlen
; Output: d0=0 success, d0=-1 on order violation or exhausted pool
; Description: Appends a GTYP_STRGADGET. The designer supplies the OUTER
;              rectangle, so the gadget rectangle (which for a string gadget is
;              the text area) is inset by 2 pixels on every side and the Border
;              polyline is placed at -2 to re-draw the outer frame (spec 4.2).
; Notes: buf and undo must each point at >= maxlen WRITABLE bytes; maxlen
;        counts the terminating NUL.
; -----------------------------------------------------------------------------
GuiAddEditBox:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    tst.w gui_building
    beq .gae_fail
    tst.w gui_shown
    bne .gae_fail

    move.w gui_ngads,d7
    cmp.w #GUI_MAX_GADGETS,d7
    bge .gae_fail

    bsr gui_slot_ptrs               ; d7 -> a0=gad a1=bord a2=xy a3=itext a4=si
    lea BD_SIZEOF(a1),a6            ; a6 = bord2
    lea 12(a2),a3                   ; a3 = xy2

    move.l 20(a5),d4                ; d4 = outer w
    move.l 24(a5),d5                ; d5 = outer h

    ; ---- Gadget: text area = outer rect inset by 2 ----
    clr.l GG_NEXTGADGET(a0)
    move.l 12(a5),d0
    addq.w #2,d0
    move.w d0,GG_LEFTEDGE(a0)
    move.l 16(a5),d0
    addq.w #2,d0
    move.w d0,GG_TOPEDGE(a0)
    move.w d4,d0
    subq.w #4,d0
    move.w d0,GG_WIDTH(a0)
    move.w d5,d0
    subq.w #4,d0
    move.w d0,GG_HEIGHT(a0)
    ; GFLG_TABCYCLE is V36+, and GuiInit demands V37, so it is always safe here
    move.w #GFLG_GADGHCOMP|GFLG_TABCYCLE,GG_FLAGS(a0)
    move.w #GACT_RELVERIFY,GG_ACTIVATION(a0)
    move.w #GTYP_STRGADGET,GG_GADGETTYPE(a0)
    move.l a1,GG_GADGETRENDER(a0)
    clr.l GG_SELECTRENDER(a0)
    clr.l GG_GADGETTEXT(a0)
    clr.l GG_MUTUALEXCLUDE(a0)
    move.l a4,GG_SPECIALINFO(a0)
    move.l 8(a5),d0
    move.w d0,GG_GADGETID(a0)
    clr.l GG_USERDATA(a0)

    ; ---- Border 1 (Top and Left: Pen 1 Black recessed shadow) ----
    clr.w BD_LEFTEDGE(a1)
    clr.w BD_TOPEDGE(a1)
    move.b #1,BD_FRONTPEN(a1)
    clr.b BD_BACKPEN(a1)
    move.b #JAM1,BD_DRAWMODE(a1)
    move.b #3,BD_COUNT(a1)
    move.l a2,BD_XY(a1)
    move.l a6,BD_NEXTBORDER(a1)

    ; ---- Border 1 polyline: (-2, h-3) -> (-2, -2) -> (w-3, -2) ----
    move.w d4,d2
    sub.w #3,d2                     ; d2 = w-3
    move.w d5,d3
    sub.w #3,d3                     ; d3 = h-3
    move.w #-2,d1
    move.w d1,0(a2)
    move.w d3,2(a2)
    move.w d1,4(a2)
    move.w d1,6(a2)
    move.w d2,8(a2)
    move.w d1,10(a2)

    ; ---- Border 2 (Bottom and Right: Pen 2 White recessed highlight) ----
    clr.w BD_LEFTEDGE(a6)
    clr.w BD_TOPEDGE(a6)
    move.b #2,BD_FRONTPEN(a6)
    clr.b BD_BACKPEN(a6)
    move.b #JAM1,BD_DRAWMODE(a6)
    move.b #3,BD_COUNT(a6)
    move.l a3,BD_XY(a6)
    clr.l BD_NEXTBORDER(a6)

    ; ---- Border 2 polyline: (w-3, -2) -> (w-3, h-3) -> (-2, h-3) ----
    move.w d4,d2
    sub.w #3,d2                     ; d2 = w-3
    move.w d5,d3
    sub.w #3,d3                     ; d3 = h-3
    move.w #-2,d1
    move.w d2,0(a3)
    move.w d1,2(a3)
    move.w d2,4(a3)
    move.w d3,6(a3)
    move.w d1,8(a3)
    move.w d3,10(a3)

    ; ---- StringInfo ----
    move.l 28(a5),SI_BUFFER(a4)
    move.l 32(a5),SI_UNDOBUFFER(a4)
    clr.w SI_BUFFERPOS(a4)
    move.l 36(a5),d0
    move.w d0,SI_MAXCHARS(a4)
    clr.w SI_DISPPOS(a4)
    clr.w SI_UNDOPOS(a4)
    clr.w SI_NUMCHARS(a4)
    clr.w SI_DISPCOUNT(a4)
    clr.w SI_CLEFT(a4)
    clr.w SI_CTOP(a4)
    clr.l SI_EXTENSION(a4)
    clr.l SI_LONGINT(a4)
    clr.l SI_ALTKEYMAP(a4)

    ; the caller's buffer may hold garbage; make it a valid empty C string
    move.l 28(a5),d0
    beq .gae_no_buf
    move.l d0,a6
    clr.b (a6)
.gae_no_buf:
    move.l 32(a5),d0
    beq .gae_no_undo
    move.l d0,a6
    clr.b (a6)
.gae_no_undo:

    bsr gui_link_gadget
    addq.w #1,gui_ngads
    moveq #0,d0
    bra .gae_done

.gae_fail:
    moveq #-1,d0

.gae_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; GuiAddCheckBox(id,x,y,w,h,caption,checked) -> int
; A toggle-select bool gadget. Intuition owns the selected flag; GuiGetCheckBox
; exposes it to generated handlers.
; -----------------------------------------------------------------------------
GuiAddCheckBox:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5
    tst.w gui_building
    beq .fail
    move.w gui_ngads,d7
    cmp.w #GUI_MAX_GADGETS,d7
    bge .fail
    bsr gui_slot_ptrs
    clr.l GG_NEXTGADGET(a0)
    move.l 12(a5),d0
    move.w d0,GG_LEFTEDGE(a0)
    move.l 16(a5),d0
    move.w d0,GG_TOPEDGE(a0)
    move.l 20(a5),d0
    move.w d0,GG_WIDTH(a0)
    move.l 24(a5),d0
    move.w d0,GG_HEIGHT(a0)
    move.w #GFLG_GADGHBOX,GG_FLAGS(a0)
    tst.l 32(a5)
    beq .unchecked
    or.w #GFLG_SELECTED,GG_FLAGS(a0)
.unchecked:
    move.w #GACT_RELVERIFY|GACT_TOGGLESELECT,GG_ACTIVATION(a0)
    move.w #GTYP_BOOLGADGET,GG_GADGETTYPE(a0)
    clr.l GG_GADGETRENDER(a0)
    clr.l GG_SELECTRENDER(a0)
    move.l a3,GG_GADGETTEXT(a0)
    move.b #1,IT_FRONTPEN(a3)
    clr.b IT_BACKPEN(a3)
    move.b #JAM1,IT_DRAWMODE(a3)
    clr.b IT_PAD(a3)
    move.w #16,IT_LEFTEDGE(a3)
    move.w #3,IT_TOPEDGE(a3)
    clr.l IT_ITEXTFONT(a3)
    move.l 28(a5),IT_ITEXT(a3)
    clr.l IT_NEXTTEXT(a3)
    clr.l GG_SPECIALINFO(a0)
    move.l 8(a5),d0
    move.w d0,GG_GADGETID(a0)
    clr.l GG_USERDATA(a0)
    move.w d7,d0
    add.w d0,d0
    lea gui_widget_kind,a1
    move.w #GUI_WIDGET_CHECKBOX,(a1,d0.w)
    bsr gui_link_gadget
    addq.w #1,gui_ngads
    moveq #0,d0
    bra .done
.fail:
    moveq #-1,d0
.done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; GuiAddList(id,x,y,w,h,labels,count,selected) -> int
; labels is a table of NUL-terminated string pointers. Rows are Topaz-8 high;
; scrolling and multi-select are intentionally outside this compact runtime.
; -----------------------------------------------------------------------------
GuiAddList:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5
    tst.w gui_building
    beq .fail
    move.w gui_ngads,d7
    cmp.w #GUI_MAX_GADGETS,d7
    bge .fail
    move.l 28(a5),d6
    beq .fail
    move.l 32(a5),d5
    ble .fail
    move.l 36(a5),d4
    cmp.l d5,d4
    bge .fail
    bsr gui_slot_ptrs
    clr.l GG_NEXTGADGET(a0)
    move.l 12(a5),d0
    move.w d0,GG_LEFTEDGE(a0)
    move.l 16(a5),d0
    move.w d0,GG_TOPEDGE(a0)
    move.l 20(a5),d0
    move.w d0,GG_WIDTH(a0)
    move.l 24(a5),d0
    move.w d0,GG_HEIGHT(a0)
    move.w #GFLG_GADGHBOX,GG_FLAGS(a0)
    move.w #GACT_RELVERIFY,GG_ACTIVATION(a0)
    move.w #GTYP_BOOLGADGET,GG_GADGETTYPE(a0)
    clr.l GG_GADGETRENDER(a0)
    clr.l GG_SELECTRENDER(a0)
    move.l a3,GG_GADGETTEXT(a0)
    move.b #1,IT_FRONTPEN(a3)
    clr.b IT_BACKPEN(a3)
    move.b #JAM1,IT_DRAWMODE(a3)
    clr.b IT_PAD(a3)
    move.w #2,IT_LEFTEDGE(a3)
    move.w #2,IT_TOPEDGE(a3)
    clr.l IT_ITEXTFONT(a3)
    move.w d4,d0
    lsl.w #2,d0
    move.l d6,a6
    move.l (a6,d0.w),IT_ITEXT(a3)
    clr.l IT_NEXTTEXT(a3)
    clr.l GG_SPECIALINFO(a0)
    move.l 8(a5),d0
    move.w d0,GG_GADGETID(a0)
    clr.l GG_USERDATA(a0)
    move.w d7,d0
    add.w d0,d0
    lea gui_widget_kind,a1
    move.w #GUI_WIDGET_LIST,(a1,d0.w)
    move.w d7,d0
    lsl.w #2,d0
    lea gui_list_labels,a1
    move.l d6,(a1,d0.w)
    move.w d7,d0
    add.w d0,d0
    lea gui_list_count,a1
    move.w d5,(a1,d0.w)
    lea gui_list_selected,a1
    move.w d4,(a1,d0.w)
    bsr gui_link_gadget
    addq.w #1,gui_ngads
    moveq #0,d0
    bra .done
.fail:
    moveq #-1,d0
.done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; GuiAddBitmap(id,x,y,w,h,image) -> int. image is a graphics/Image structure.
; -----------------------------------------------------------------------------
GuiAddBitmap:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5
    tst.w gui_building
    beq .fail
    move.w gui_ngads,d7
    cmp.w #GUI_MAX_GADGETS,d7
    bge .fail
    move.l 28(a5),d0
    beq .fail
    bsr gui_slot_ptrs
    clr.l GG_NEXTGADGET(a0)
    move.l 12(a5),d0
    move.w d0,GG_LEFTEDGE(a0)
    move.l 16(a5),d0
    move.w d0,GG_TOPEDGE(a0)
    move.l 20(a5),d0
    move.w d0,GG_WIDTH(a0)
    move.l 24(a5),d0
    move.w d0,GG_HEIGHT(a0)
    move.w #GFLG_GADGIMAGE,GG_FLAGS(a0)
    move.w #GACT_RELVERIFY,GG_ACTIVATION(a0)
    move.w #GTYP_BOOLGADGET,GG_GADGETTYPE(a0)
    move.l 28(a5),GG_GADGETRENDER(a0)
    clr.l GG_SELECTRENDER(a0)
    clr.l GG_GADGETTEXT(a0)
    clr.l GG_SPECIALINFO(a0)
    move.l 8(a5),d0
    move.w d0,GG_GADGETID(a0)
    clr.l GG_USERDATA(a0)
    move.w d7,d0
    add.w d0,d0
    lea gui_widget_kind,a1
    move.w #GUI_WIDGET_BITMAP,(a1,d0.w)
    bsr gui_link_gadget
    addq.w #1,gui_ngads
    moveq #0,d0
    bra .done
.fail:
    moveq #-1,d0
.done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiShow
; Input: none
; Output: d0=Window* on success, 0 if OpenWindow failed, -1 on order violation
; Description: Opens the window, clears its client area, adds the built gadget
;              list, then caches RPort/UserPort/signal mask and paints labels.
; -----------------------------------------------------------------------------
GuiShow:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)

    tst.w gui_building
    beq .gsh_order
    tst.w gui_shown
    bne .gsh_order
    move.l gui_window,d0
    bne .gsh_order

    move.l gui_int_base,d0
    beq .gsh_order
    lea gui_nw,a0
    move.l gui_firstgad,NW_FIRSTGADGET(a0)   ; install gadgets before open for hit-testing
    move.l d0,a6
    lea gui_nw,a0
    jsr _LVOOpenWindow(a6)
    move.l d0,gui_window
    beq .gsh_zero

    move.l d0,a0
    move.l WD_RPORT(a0),gui_rport
    move.l WD_USERPORT(a0),a1
    move.l a1,gui_userport
    moveq #0,d1
    move.b MP_SIGBIT(a1),d1
    moveq #1,d0
    lsl.l d1,d0
    move.l d0,gui_sigmask

    move.w #1,gui_shown
    clr.w gui_building

    ; Bring the freshly opened window to front and give it input focus, so it
    ; is not left behind an existing screen/window (e.g. a boot Shell).
    move.l gui_int_base,a6
    move.l gui_window,a0
    jsr _LVOWindowToFront(a6)
    move.l gui_int_base,a6
    move.l gui_window,a0
    jsr _LVOActivateWindow(a6)

    bsr gui_clear_client_area

    move.l gui_firstgad,d0
    beq .gsh_labels
    move.l gui_int_base,a6
    move.l gui_firstgad,a0
    move.l gui_window,a1
    sub.l a2,a2
    moveq #-1,d0
    jsr _LVORefreshGList(a6)

.gsh_labels:
    bsr gui_redraw_buttons
    bsr gui_redraw_lists
    bsr gui_redraw_labels

    move.l gui_window,d0
    bra .gsh_done

.gsh_zero:
    moveq #0,d0
    bra .gsh_done

.gsh_order:
    moveq #-1,d0

.gsh_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiCloseWindow
; Input: none
; Output: none (d0 undefined)
; Description: Closes the window using the documented safe protocol.
; Notes: Idempotent; safe if the window was never opened.
; -----------------------------------------------------------------------------
GuiCloseWindow:
    link a6,#0
    movem.l d0-d7/a0-a6,-(sp)
    bsr gui_do_close_window
    movem.l (sp)+,d0-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiWaitEvent
; Input: none
; Output: d0 = GUI_EVT_* class code, or -1 if the window is not shown
; Description: Blocks on Wait(sigmask), takes ONE IntuiMessage, snapshots
;              class/code/IAddress/mouse BEFORE ReplyMsg (gotcha 1), replies
;              it, then decodes from the copies only.
; Notes: IDCMP_REFRESHWINDOW is answered internally with BeginRefresh /
;        redraw labels / EndRefresh(win,1) and reported as GUI_EVT_REFRESH.
;        Unknown classes are replied and skipped, never left unreplied.
; -----------------------------------------------------------------------------
GuiWaitEvent:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)

    tst.w gui_shown
    beq .gwe_bad
    move.l gui_userport,d0
    beq .gwe_bad

; Signals are a single latched bit, not a counter: PutMsg()'s Signal() call
; coalesces if two messages arrive before Wait() is next called, so a message
; already queued from an earlier (already-consumed) signal must always be
; drained BEFORE blocking again, or it can starve forever behind Wait().
.gwe_drain:
    move.l ExecBase,a6
    move.l gui_userport,d0
    beq .gwe_bad
    move.l d0,a0
    jsr _LVOGetMsg(a6)
    move.l d0,a3
    tst.l d0
    bne .gwe_got

.gwe_wait:
    move.l ExecBase,a6
    move.l gui_sigmask,d0
    jsr _LVOWait(a6)
    bra .gwe_drain

.gwe_got:

    ; ---- snapshot BEFORE ReplyMsg ----
    move.l IM_CLASS(a3),d4
    moveq #0,d2
    move.w IM_CODE(a3),d2
    move.l IM_IADDRESS(a3),d3
    move.w IM_MOUSEX(a3),gui_evt_mx
    move.w IM_MOUSEY(a3),gui_evt_my
    move.l a3,a1
    jsr _LVOReplyMsg(a6)

    ; ---- decode from the copies only ----
    move.l d2,gui_evt_code
    clr.l gui_evt_id

    btst #IDCMPB_CLOSEWINDOW,d4
    bne .gwe_close
    btst #IDCMPB_GADGETUP,d4
    bne .gwe_gadup
    btst #IDCMPB_GADGETDOWN,d4
    bne .gwe_gaddown
    btst #IDCMPB_VANILLAKEY,d4
    bne .gwe_key
    btst #IDCMPB_MOUSEBUTTONS,d4
    bne .gwe_mouse
    btst #IDCMPB_REFRESHWINDOW,d4
    bne .gwe_refresh
    bra .gwe_drain                  ; unknown class: already replied, take next

.gwe_close:
    moveq #GUI_EVT_CLOSE,d0
    bra .gwe_out

.gwe_gadup:
    move.l d3,d0
    beq .gwe_none
    move.l d3,a0
    moveq #0,d0
    move.w GG_GADGETID(a0),d0
    move.l d0,gui_evt_id
    move.w GG_GADGETTYPE(a0),d0
    and.w #GTYP_GTYPEMASK,d0
    cmp.w #GTYP_STRGADGET,d0
    beq .gwe_is_str
    bsr gui_get_slot_index
    tst.w d0
    bmi .gwe_none
    add.w d0,d0
    lea gui_widget_kind,a1
    move.w (a1,d0.w),d1
    cmp.w #GUI_WIDGET_CHECKBOX,d1
    beq .gwe_is_checkbox
    cmp.w #GUI_WIDGET_LIST,d1
    beq .gwe_is_list
    cmp.w #GUI_WIDGET_BITMAP,d1
    beq .gwe_none
    moveq #GUI_EVT_BUTTON,d0
    bra .gwe_out
.gwe_is_str:
    moveq #GUI_EVT_STRING,d0
    bra .gwe_out
.gwe_is_checkbox:
    moveq #GUI_EVT_CHECKBOX,d0
    bra .gwe_out
.gwe_is_list:
    move.w d0,d1
    move.w gui_evt_my,d0
    sub.w GG_TOPEDGE(a0),d0
    subq.w #2,d0
    bmi .gwe_none
    lsr.w #3,d0
    add.w d1,d1
    lea gui_list_count,a1
    cmp.w (a1,d1.w),d0
    bge .gwe_none
    lea gui_list_selected,a1
    move.w d0,(a1,d1.w)
    lsl.w #1,d0
    move.w d1,d2
    add.w d2,d2
    lea gui_list_labels,a1
    move.l (a1,d2.w),a1
    move.l GG_GADGETTEXT(a0),a2
    move.l (a1,d0.w),IT_ITEXT(a2)
    bsr gui_refresh_gadget
    bsr gui_redraw_lists
    moveq #GUI_EVT_LIST,d0
    bra .gwe_out

.gwe_gaddown:
    move.l d3,d0
    beq .gwe_press_out
    move.l d3,a0
    moveq #0,d0
    move.w GG_GADGETID(a0),d0
    move.l d0,gui_evt_id
.gwe_press_out:
    moveq #GUI_EVT_PRESS,d0
    bra .gwe_out

.gwe_key:
    moveq #GUI_EVT_KEY,d0
    bra .gwe_out

.gwe_mouse:
    moveq #GUI_EVT_MOUSE,d0
    bra .gwe_out

.gwe_refresh:
    move.l gui_int_base,a6
    move.l gui_window,a0
    jsr _LVOBeginRefresh(a6)
    bsr gui_clear_client_area
    move.l gui_firstgad,d0
    beq .gwer_labels
    move.l gui_int_base,a6
    move.l gui_firstgad,a0
    move.l gui_window,a1
    sub.l a2,a2
    moveq #-1,d0
    jsr _LVORefreshGList(a6)
.gwer_labels:
    bsr gui_redraw_buttons
    bsr gui_redraw_lists
    bsr gui_redraw_labels
    move.l gui_int_base,a6
    move.l gui_window,a0
    moveq #1,d0
    jsr _LVOEndRefresh(a6)
    moveq #GUI_EVT_REFRESH,d0
    bra .gwe_out

.gwe_none:
    moveq #GUI_EVT_NONE,d0
    bra .gwe_out

.gwe_bad:
    moveq #-1,d0

.gwe_out:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiGetEventID
; Input: none
; Output: d0 = gg_GadgetID of the last gadget event, 0 if none
; Description: Reads the value latched by GuiWaitEvent().
; Notes: Gadget ID 0 is reserved for "no gadget" (gotcha 12).
; -----------------------------------------------------------------------------
GuiGetEventID:
    link a6,#0
    move.l gui_evt_id,d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiGetEventCode
; Input: none
; Output: d0 = im_Code of the last event (ASCII for GUI_EVT_KEY)
; Description: Reads the value latched by GuiWaitEvent().
; Notes: Zero-extended from the UWORD im_Code.
; -----------------------------------------------------------------------------
GuiGetEventCode:
    link a6,#0
    move.l gui_evt_code,d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiGetEventX
; Input: none
; Output: d0 = im_MouseX of the last event, sign-extended
; Description: Reads the value latched by GuiWaitEvent().
; Notes: Window-relative coordinate.
; -----------------------------------------------------------------------------
GuiGetEventX:
    link a6,#0
    move.w gui_evt_mx,d0
    ext.l d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiGetEventY
; Input: none
; Output: d0 = im_MouseY of the last event, sign-extended
; Description: Reads the value latched by GuiWaitEvent().
; Notes: Window-relative coordinate.
; -----------------------------------------------------------------------------
GuiGetEventY:
    link a6,#0
    move.w gui_evt_my,d0
    ext.l d0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; GuiGetCheckBox(id) -> int. Returns 1 if selected, 0 if clear or not found.
; -----------------------------------------------------------------------------
GuiGetCheckBox:
    link a6,#0
    movem.l d1-d2/a0,-(sp)
    move.l 8(a6),d0
    bsr gui_find_gadget
    move.l a0,d1
    beq .done
    bsr gui_get_slot_index
    add.w d0,d0
    lea gui_widget_kind,a1
    cmp.w #GUI_WIDGET_CHECKBOX,(a1,d0.w)
    bne .done
    moveq #0,d0
    btst #7,GG_FLAGS(a0)
    beq .done
    moveq #1,d0
.done:
    movem.l (sp)+,d1-d2/a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; GuiGetListSelected(id) -> int. Returns selected row, or -1 if not a list.
; -----------------------------------------------------------------------------
GuiGetListSelected:
    link a6,#0
    movem.l d1-d2/a0,-(sp)
    move.l 8(a6),d0
    bsr gui_find_gadget
    move.l a0,d1
    beq .none
    bsr gui_get_slot_index
    add.w d0,d0
    lea gui_widget_kind,a1
    cmp.w #GUI_WIDGET_LIST,(a1,d0.w)
    bne .none
    lea gui_list_selected,a1
    move.w (a1,d0.w),d0
    ext.l d0
    bra .done
.none:
    moveq #-1,d0
.done:
    movem.l (sp)+,d1-d2/a0
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiGetEditText
; Input: 8(a6)=id
; Output: d0 = si_Buffer pointer of that string gadget, or 0
; Description: Looks the gadget up by gg_GadgetID and returns its buffer.
; Notes: The buffer contents are only stable after a GUI_EVT_STRING event
;        (gotcha 13).
; -----------------------------------------------------------------------------
GuiGetEditText:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    move.l 8(a5),d0
    bsr gui_find_string_gadget
    move.l a0,d0
    beq .gget_none
    move.l GG_SPECIALINFO(a0),d0
    beq .gget_none
    move.l d0,a1
    move.l SI_BUFFER(a1),d0
    bra .gget_done

.gget_none:
    moveq #0,d0

.gget_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiSetEditText
; Input: 8(a6)=id, 12(a6)=text (NUL-terminated)
; Output: d0=0 success, d0=-1 if the gadget does not exist
; Description: Copies text into si_Buffer clamped to si_MaxChars-1, resets
;              si_BufferPos/si_DispPos/si_NumChars and refreshes the gadget.
; Notes: si_Buffer must be writable RAM (gotcha 7).
; -----------------------------------------------------------------------------
GuiSetEditText:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    move.l 8(a5),d0
    bsr gui_find_string_gadget
    move.l a0,d0
    beq .gset_fail
    move.l a0,a4                    ; a4 = Gadget*
    move.l GG_SPECIALINFO(a0),d0
    beq .gset_fail
    move.l d0,a3                    ; a3 = StringInfo*
    move.l SI_BUFFER(a3),d0
    beq .gset_fail
    move.l d0,a0                    ; a0 = dest
    move.l 12(a5),d0
    beq .gset_fail
    move.l d0,a1                    ; a1 = src

    moveq #0,d2
    move.w SI_MAXCHARS(a3),d2
    subq.l #1,d2                    ; room excluding the terminating NUL
    ble .gset_terminate
    moveq #0,d3

.gset_copy:
    tst.l d2
    beq .gset_terminate
    move.b (a1)+,d0
    beq .gset_terminate
    move.b d0,(a0)+
    addq.l #1,d3
    subq.l #1,d2
    bra .gset_copy

.gset_terminate:
    clr.b (a0)
    move.w d3,SI_NUMCHARS(a3)
    clr.w SI_BUFFERPOS(a3)
    clr.w SI_DISPPOS(a3)

    move.l a4,a0
    bsr gui_refresh_gadget
    moveq #0,d0
    bra .gset_done

.gset_fail:
    moveq #-1,d0

.gset_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiSetLabelText
; Input: 8(a6)=id, 12(a6)=text
; Output: d0=0 success, d0=-1 if the label does not exist
; Description: Repoints a label's it_IText and repaints it.
; Notes: The label IntuiText uses JAM2, so the new string overwrites the old
;        one; a strictly shorter replacement still leaves the tail of the
;        previous text on screen - call GuiRedraw() if that matters.
;        The string must outlive the window (gotcha 8).
; -----------------------------------------------------------------------------
GuiSetLabelText:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    move.l 8(a5),d0
    bsr gui_find_label              ; -> a0 = IntuiText*, a1 = xy or a0 = 0
    move.l a0,d0
    beq .glbl_fail

    move.l 12(a5),IT_ITEXT(a0)

    move.l gui_rport,d0
    beq .glbl_ok
    move.l a0,a3                    ; a3 = IntuiText* (before a0 is overwritten)
    move.l a1,a2                    ; a2 = xy pointer
    move.l gui_int_base,a6
    move.l gui_rport,a0
    move.l a3,a1
    move.w (a2),d0
    ext.l d0
    move.w 2(a2),d1
    ext.l d1
    jsr _LVOPrintIText(a6)

.glbl_ok:
    moveq #0,d0
    bra .glbl_done

.glbl_fail:
    moveq #-1,d0

.glbl_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiEnableWidget
; Input: 8(a6)=id, 12(a6)=enable (0 = disable, non-zero = enable)
; Output: d0=0 success, d0=-1 if the gadget does not exist
; Description: Toggles GFLG_DISABLED and refreshes the gadget.
; Notes: Only meaningful for gadgets; labels are not affected.
; -----------------------------------------------------------------------------
GuiEnableWidget:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    move.l 8(a5),d0
    bsr gui_find_gadget
    move.l a0,d0
    beq .gen_fail

    move.w GG_FLAGS(a0),d1
    tst.l 12(a5)
    beq .gen_disable
    and.w #$FFFF-GFLG_DISABLED,d1
    bra .gen_store
.gen_disable:
    or.w #GFLG_DISABLED,d1
.gen_store:
    move.w d1,GG_FLAGS(a0)

    bsr gui_refresh_gadget
    moveq #0,d0
    bra .gen_done

.gen_fail:
    moveq #-1,d0

.gen_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiActivateEdit
; Input: 8(a6)=id
; Output: d0=0 success, d0=-1 if the gadget does not exist or no window
; Description: Puts the text cursor in a string gadget via ActivateGadget().
; Notes: Only valid while the window is open.
; -----------------------------------------------------------------------------
GuiActivateEdit:
    link a6,#0
    movem.l d1-d7/a0-a6,-(sp)
    move.l a6,a5

    move.l gui_window,d0
    beq .gact_fail
    move.l 8(a5),d0
    bsr gui_find_string_gadget
    move.l a0,d0
    beq .gact_fail

    move.l gui_int_base,a6
    move.l gui_window,a1
    sub.l a2,a2
    jsr _LVOActivateGadget(a6)

    moveq #0,d0
    bra .gact_done

.gact_fail:
    moveq #-1,d0

.gact_done:
    movem.l (sp)+,d1-d7/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: GuiRedraw
; Input: none
; Output: none (d0 undefined)
; Description: Full repaint: RefreshGList over the whole gadget list plus all
;              labels.
; Notes: Harmless when the window is closed.
; -----------------------------------------------------------------------------
GuiRedraw:
    link a6,#0
    movem.l d0-d7/a0-a6,-(sp)

    move.l gui_window,d0
    beq .grd_done

    bsr gui_clear_client_area

    move.l gui_firstgad,d0
    beq .grd_labels

    move.l gui_int_base,a6
    move.l gui_firstgad,a0
    move.l gui_window,a1
    sub.l a2,a2
    moveq #-1,d0
    jsr _LVORefreshGList(a6)

.grd_labels:
    bsr gui_redraw_buttons
    bsr gui_redraw_lists
    bsr gui_redraw_labels

.grd_done:
    movem.l (sp)+,d0-d7/a0-a6
    unlk a6
    rts

; =============================================================================
; Internal helpers - not XDEF'd
; =============================================================================

; -----------------------------------------------------------------------------
; gui_slot_ptrs
; Input:  d7.w = slot index
; Output: a0 = &gui_gadgets[i]  a1 = &gui_borders[i]  a2 = &gui_bordxy[i]
;         a3 = &gui_itexts[i]   a4 = &gui_strinfo[i]
; Clobbers: d0
; -----------------------------------------------------------------------------
gui_slot_ptrs:
    move.w d7,d0
    mulu.w #GG_SIZEOF,d0
    lea gui_gadgets,a0
    add.l d0,a0

    move.w d7,d0
    mulu.w #BD_SIZEOF*2,d0
    lea gui_borders,a1
    add.l d0,a1

    move.w d7,d0
    mulu.w #GUI_BORDXY_SIZEOF,d0
    lea gui_bordxy,a2
    add.l d0,a2

    move.w d7,d0
    mulu.w #IT_SIZEOF,d0
    lea gui_itexts,a3
    add.l d0,a3

    move.w d7,d0
    mulu.w #SI_SIZEOF,d0
    lea gui_strinfo,a4
    add.l d0,a4
    rts

; -----------------------------------------------------------------------------
; gui_link_gadget
; Input:  a0 = Gadget* to append
; Output: none
; Description: Appends to the singly linked list and keeps it NUL terminated
;              (gotcha 5). List order is hit-test and TAB order (gotcha 6).
; Clobbers: d0, a1
; -----------------------------------------------------------------------------
gui_link_gadget:
    clr.l GG_NEXTGADGET(a0)
    move.l gui_lastgad,d0
    beq .glg_first
    move.l d0,a1
    move.l a0,GG_NEXTGADGET(a1)
    bra .glg_tail
.glg_first:
    move.l a0,gui_firstgad
.glg_tail:
    move.l a0,gui_lastgad
    rts

; -----------------------------------------------------------------------------
; gui_strlen
; Input:  d0 = pointer to a NUL-terminated string (may be 0)
; Output: d0 = length in bytes, zero-extended
; Clobbers: a0
; -----------------------------------------------------------------------------
gui_strlen:
    move.l d0,a0
    tst.l d0
    moveq #0,d0
    beq .gsl_done
.gsl_loop:
    tst.b (a0)+
    beq .gsl_done
    addq.l #1,d0
    bra .gsl_loop
.gsl_done:
    rts

; -----------------------------------------------------------------------------
; gui_find_gadget
; Input:  d0.w = gadget id
; Output: a0 = Gadget* or 0
; Clobbers: d1, d2
; -----------------------------------------------------------------------------
gui_find_gadget:
    move.w gui_ngads,d2
    lea gui_gadgets,a0
    bra .gfg_test
.gfg_loop:
    move.w GG_GADGETID(a0),d1
    cmp.w d0,d1
    beq .gfg_out
    lea GG_SIZEOF(a0),a0
    subq.w #1,d2
.gfg_test:
    tst.w d2
    bne .gfg_loop
    sub.l a0,a0
.gfg_out:
    rts

; -----------------------------------------------------------------------------
; gui_get_slot_index
; Input: a0 = pointer within gui_gadgets. Output: d0.w = slot, or -1.
; -----------------------------------------------------------------------------
gui_get_slot_index:
    lea gui_gadgets,a1
    moveq #0,d0
.ggsi_loop:
    cmpa.l a1,a0
    beq .ggsi_done
    lea GG_SIZEOF(a1),a1
    addq.w #1,d0
    cmp.w gui_ngads,d0
    blt .ggsi_loop
    moveq #-1,d0
.ggsi_done:
    rts

; -----------------------------------------------------------------------------
; gui_find_string_gadget
; Input:  d0.w = gadget id
; Output: a0 = Gadget* if it is a GTYP_STRGADGET, else 0
; Clobbers: d1, d2
; -----------------------------------------------------------------------------
gui_find_string_gadget:
    bsr gui_find_gadget
    move.l a0,d1
    beq .gfs_out
    move.w GG_GADGETTYPE(a0),d1
    and.w #GTYP_GTYPEMASK,d1
    cmp.w #GTYP_STRGADGET,d1
    beq .gfs_out
    sub.l a0,a0
.gfs_out:
    rts

; -----------------------------------------------------------------------------
; gui_find_label
; Input:  d0.w = label id
; Output: a0 = IntuiText* and a1 = &gui_label_xy[i], or a0 = 0
; Clobbers: d1, d2
; -----------------------------------------------------------------------------
gui_find_label:
    moveq #0,d2                     ; index
.gfl_loop:
    cmp.w gui_nlabels,d2
    bge .gfl_none
    move.w d2,d1
    add.w d1,d1
    lea gui_label_id,a1
    adda.w d1,a1
    move.w (a1),d1
    cmp.w d0,d1
    beq .gfl_found
    addq.w #1,d2
    bra .gfl_loop
.gfl_found:
    move.w d2,d1
    mulu.w #IT_SIZEOF,d1
    lea gui_labels,a0
    add.l d1,a0
    move.w d2,d1
    mulu.w #4,d1
    lea gui_label_xy,a1
    add.l d1,a1
    rts
.gfl_none:
    sub.l a0,a0
    sub.l a1,a1
    rts

; -----------------------------------------------------------------------------
; gui_refresh_gadget
; Input:  a0 = Gadget*
; Output: none
; Description: RefreshGList() for exactly one gadget. No-op if no window.
; Clobbers: d0, d1, a1, a2, a6
; -----------------------------------------------------------------------------
gui_refresh_gadget:
    move.l gui_window,d0
    beq .grg_done
    move.l gui_int_base,d0
    beq .grg_done
    move.l d0,a6
    move.l gui_window,a1
    sub.l a2,a2
    moveq #1,d0
    jsr _LVORefreshGList(a6)
.grg_done:
    rts

; -----------------------------------------------------------------------------
; gui_redraw_labels
; Input:  none
; Output: none
; Description: PrintIText()s every registered label at its stored offsets.
;              SMART_REFRESH redraws gadgets but never anything we drew
;              ourselves, so this is called from GuiShow, GuiRedraw and the
;              IDCMP_REFRESHWINDOW handler (gotcha 9).
; Clobbers: d0-d3, a0-a3, a6
; -----------------------------------------------------------------------------
gui_redraw_labels:
    move.l gui_rport,d0
    beq .grl_done
    move.l gui_int_base,d0
    beq .grl_done
    move.w gui_nlabels,d4
    beq .grl_done
    subq.w #1,d4
    moveq #0,d5

.grl_loop:
    move.w d5,d0
    mulu.w #IT_SIZEOF,d0
    lea gui_labels,a2
    add.l d0,a2
    move.w d5,d0
    mulu.w #4,d0
    lea gui_label_xy,a3
    add.l d0,a3

    move.l gui_int_base,a6
    move.l gui_rport,a0
    move.l a2,a1
    move.w (a3),d0
    ext.l d0
    move.w 2(a3),d1
    ext.l d1
    jsr _LVOPrintIText(a6)

    addq.w #1,d5
    dbra d4,.grl_loop

.grl_done:
    rts

; -----------------------------------------------------------------------------
; gui_redraw_buttons
; Input:  none
; Output: none
; Description: Draws Border and IntuiText imagery for bool gadgets after a
;              client-area clear. Intuition retains the active gadget list and
;              handles their selection state and IDCMP events.
; Clobbers: d0-d3, a0-a3, a6
; -----------------------------------------------------------------------------
gui_redraw_buttons:
    move.l gui_rport,d0
    beq .grb_done
    move.l gui_int_base,d0
    beq .grb_done
    move.w gui_ngads,d4
    beq .grb_done
    subq.w #1,d4
    lea gui_gadgets,a3

.grb_loop:
    move.w GG_GADGETTYPE(a3),d2
    and.w #GTYP_GTYPEMASK,d2
    cmp.w #GTYP_BOOLGADGET,d2
    bne .grb_next

    move.l a3,a0
    bsr gui_get_slot_index
    tst.w d0
    bmi .grb_next
    add.w d0,d0
    lea gui_widget_kind,a0
    move.w (a0,d0.w),d2
    cmp.w #GUI_WIDGET_BITMAP,d2
    beq .grb_next
    cmp.w #GUI_WIDGET_LIST,d2
    beq .grb_next
    cmp.w #GUI_WIDGET_BUTTON,d2
    bne .grb_text

    move.l gui_int_base,a6
    move.l gui_rport,a0
    move.l GG_GADGETRENDER(a3),a1
    move.w GG_LEFTEDGE(a3),d0
    ext.l d0
    move.w GG_TOPEDGE(a3),d1
    ext.l d1
    jsr _LVODrawBorder(a6)

.grb_text:
    move.l gui_int_base,a6
    move.l gui_rport,a0
    move.l GG_GADGETTEXT(a3),a1
    move.l a1,d0
    tst.l d0
    beq .grb_next
    move.w GG_LEFTEDGE(a3),d0
    ext.l d0
    move.w GG_TOPEDGE(a3),d1
    ext.l d1
    jsr _LVOPrintIText(a6)

.grb_next:
    lea GG_SIZEOF(a3),a3
    dbra d4,.grb_loop

.grb_done:
    rts

; -----------------------------------------------------------------------------
; gui_redraw_lists
; Draws every fixed-height (Topaz-8) list row. The selected row is inverse
; video; the enclosing GADGHBOX is drawn by Intuition during RefreshGList.
; -----------------------------------------------------------------------------
gui_redraw_lists:
    move.l gui_rport,d0
    beq .grls_done
    move.w gui_ngads,d4
    beq .grls_done
    subq.w #1,d4
    lea gui_gadgets,a3

.grls_gadget:
    move.l a3,a0
    bsr gui_get_slot_index
    tst.w d0
    bmi .grls_next
    move.w d0,d5
    add.w d0,d0
    lea gui_widget_kind,a0
    cmp.w #GUI_WIDGET_LIST,(a0,d0.w)
    bne .grls_next
    lea gui_list_count,a0
    move.w (a0,d0.w),d6
    beq .grls_next
    subq.w #1,d6
    lea gui_list_labels,a1
    move.w d5,d0
    lsl.w #2,d0
    move.l (a1,d0.w),a1
    lea gui_list_selected,a0
    move.w d5,d0
    add.w d0,d0
    move.w (a0,d0.w),d5
    moveq #0,d7

.grls_row:
    move.l GG_GADGETTEXT(a3),a2
    move.w d7,d0
    lsl.w #2,d0
    move.l (a1,d0.w),IT_ITEXT(a2)
    move.w d7,d0
    lsl.w #3,d0
    addq.w #2,d0
    move.w d0,IT_TOPEDGE(a2)
    move.b #JAM1,IT_DRAWMODE(a2)
    cmp.w d5,d7
    bne .grls_draw
    or.b #INVERSVID,IT_DRAWMODE(a2)
.grls_draw:
    move.l gui_int_base,a6
    move.l gui_rport,a0
    move.l a2,a1
    move.w GG_LEFTEDGE(a3),d0
    ext.l d0
    move.w GG_TOPEDGE(a3),d1
    ext.l d1
    jsr _LVOPrintIText(a6)
    addq.w #1,d7
    dbra d6,.grls_row

.grls_next:
    lea GG_SIZEOF(a3),a3
    dbra d4,.grls_gadget
.grls_done:
    rts

; -----------------------------------------------------------------------------
; gui_do_close_window
; Input:  none
; Output: none
; Description: The documented safe close protocol (gotcha 3 and 4):
;              Forbid -> drain and reply every pending IntuiMessage ->
;              detach the UserPort -> ModifyIDCMP(win,0) -> RemoveGList ->
;              CloseWindow -> Permit.
; Notes: This deviates from the literal ordering in spec section 6 gotcha 3,
;        which puts ModifyIDCMP(win,0) BEFORE the drain loop. ModifyIDCMP with
;        a zero mask deletes the window's own UserPort, so draining afterwards
;        would be a use-after-free. The order used here is the one from the
;        Intuition RKM CloseWindowSafely() example and has the same effect.
;        Idempotent; safe when the window was never opened.
; Clobbers: d0-d3, a0-a3, a6
; -----------------------------------------------------------------------------
gui_do_close_window:
    move.l gui_window,d0
    beq .gdc_done
    move.l gui_int_base,d0
    beq .gdc_done

    move.l ExecBase,a6
    jsr _LVOForbid(a6)

.gdc_drain:
    move.l gui_userport,d0
    beq .gdc_drained
    move.l ExecBase,a6
    move.l gui_userport,a0
    jsr _LVOGetMsg(a6)
    tst.l d0
    beq .gdc_drained
    move.l d0,a1
    jsr _LVOReplyMsg(a6)
    bra .gdc_drain

.gdc_drained:
    ; detach the port before it is deleted, then stop all IDCMP traffic
    move.l gui_window,a0
    clr.l WD_USERPORT(a0)
    clr.l gui_userport
    clr.l gui_sigmask

    move.l gui_int_base,a6
    move.l gui_window,a0
    moveq #0,d0
    jsr _LVOModifyIDCMP(a6)

    move.l gui_firstgad,d0
    beq .gdc_noglist
    move.l gui_int_base,a6
    move.l gui_window,a0
    move.l d0,a1
    moveq #0,d0
    move.w gui_ngads,d0
    jsr _LVORemoveGList(a6)

.gdc_noglist:
    move.l gui_int_base,a6
    move.l gui_window,a0
    jsr _LVOCloseWindow(a6)

    clr.l gui_window
    clr.l gui_rport
    clr.w gui_shown
    clr.w gui_building
    move.l ExecBase,a6
    jsr _LVOPermit(a6)
.gdc_done:
    rts

; -----------------------------------------------------------------------------
; gui_clear_client_area
; Input:  none
; Output: none
; Description: Fills the interior client rectangle of the window with Pen 0
;              (Grey background).
; Clobbers: none (preserves d0-d4/a0-a2/a6)
; -----------------------------------------------------------------------------
gui_clear_client_area:
    movem.l d0-d4/a0-a2/a6,-(sp)

    move.l gui_window,d0
    beq .gcca_done
    move.l d0,a2                    ; a2 = Window*

    move.l gui_rport,d0
    beq .gcca_done
    move.l d0,a1                    ; a1 = RastPort*

    move.l gui_gfx_base,d0
    beq .gcca_done
    move.l d0,a6                    ; a6 = GfxBase*

    ; SetAPen(rp, 0)
    move.l gui_rport,a1
    moveq #0,d0
    jsr _LVOSetAPen(a6)

    ; The window RastPort is client-relative without GIMMEZEROZERO.
    ; Clear from its origin, not from the outer-window border offsets.
    move.l gui_window,a2
    move.l gui_gfx_base,a6

    moveq #0,d0                     ; d0 = xmin
    moveq #0,d1                     ; d1 = ymin

    moveq #0,d2
    move.w WD_WIDTH(a2),d2
    moveq #0,d4
    move.b WD_BORDERLEFT(a2),d4
    sub.w d4,d2
    moveq #0,d4
    move.b WD_BORDERRIGHT(a2),d4
    sub.w d4,d2
    subq.w #1,d2                    ; d2 = xmax

    moveq #0,d3
    move.w WD_HEIGHT(a2),d3
    moveq #0,d4
    move.b WD_BORDERTOP(a2),d4
    sub.w d4,d3
    move.b WD_BORDERBOTTOM(a2),d4
    sub.w d4,d3
    subq.w #1,d3                    ; d3 = ymax

    move.l gui_rport,a1
    jsr _LVORectFill(a6)

.gcca_done:
    movem.l (sp)+,d0-d4/a0-a2/a6
    rts
