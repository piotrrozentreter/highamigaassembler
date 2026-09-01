; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; gui_intuition.i - Constants and structure offsets for lib/gui_intuition.s
;
; System-friendly Intuition GUI runtime for HAS. All values are taken from
; docs/GUI_INTUITION_RUNTIME_SPEC.md sections 2 and 3.
; =============================================================================

    ifnd GUI_INTUITION_I
GUI_INTUITION_I = 1

; -----------------------------------------------------------------------------
; Library version requested by GuiInit()
; -----------------------------------------------------------------------------
GUI_LIB_VERSION     EQU 37          ; AmigaOS 2.0+. Use 0 for Kickstart 1.3.

; -----------------------------------------------------------------------------
; exec.library LVOs (also present in exec_lib.i; repeated for documentation)
; -----------------------------------------------------------------------------
; _LVOOpenLibrary   EQU -552        ; a1=name, d0=version  -> d0=base
; _LVOCloseLibrary  EQU -414        ; a1=base
; _LVOWait          EQU -318        ; d0=sigmask           -> d0=signals
; _LVOGetMsg        EQU -372        ; a0=port              -> d0=msg or 0
; _LVOReplyMsg      EQU -378        ; a1=msg
; _LVOForbid        EQU -132
; _LVOPermit        EQU -138

; -----------------------------------------------------------------------------
; intuition.library LVOs
; -----------------------------------------------------------------------------
_LVOOpenWindow      EQU -204        ; a0=NewWindow          -> d0=Window
_LVOCloseWindow     EQU -72         ; a0=Window
_LVOPrintIText      EQU -216        ; a0=RPort, a1=IText, d0=xoff, d1=yoff
_LVOAddGList        EQU -438        ; a0=Win, a1=Gad, d0=pos, d1=count, a2=0
_LVORemoveGList     EQU -444        ; a0=Win, a1=Gad, d0=count
_LVORefreshGList    EQU -432        ; a0=Gad, a1=Win, a2=0, d0=count
_LVOActivateGadget  EQU -462        ; a0=Gad, a1=Win, a2=0
_LVOModifyIDCMP     EQU -150        ; a0=Win, d0=flags
_LVOBeginRefresh    EQU -354        ; a0=Win
_LVOEndRefresh      EQU -366        ; a0=Win, d0=complete
_LVODrawBorder      EQU -108        ; a0=RPort, a1=Border, d0=xoff, d1=yoff

; -----------------------------------------------------------------------------
; exec MsgPort
; -----------------------------------------------------------------------------
MP_SIGBIT           EQU 15          ; UBYTE

; -----------------------------------------------------------------------------
; struct NewWindow - 48 bytes
; -----------------------------------------------------------------------------
NW_LEFTEDGE         EQU 0           ; WORD
NW_TOPEDGE          EQU 2           ; WORD
NW_WIDTH            EQU 4           ; WORD
NW_HEIGHT           EQU 6           ; WORD
NW_DETAILPEN        EQU 8           ; UBYTE
NW_BLOCKPEN         EQU 9           ; UBYTE
NW_IDCMPFLAGS       EQU 10          ; ULONG
NW_FLAGS            EQU 14          ; ULONG
NW_FIRSTGADGET      EQU 18          ; APTR
NW_CHECKMARK        EQU 22          ; APTR
NW_TITLE            EQU 26          ; APTR
NW_SCREEN           EQU 30          ; APTR
NW_BITMAP           EQU 34          ; APTR
NW_MINWIDTH         EQU 38          ; WORD
NW_MINHEIGHT        EQU 40          ; WORD
NW_MAXWIDTH         EQU 42          ; UWORD
NW_MAXHEIGHT        EQU 44          ; UWORD
NW_TYPE             EQU 46          ; UWORD
NW_SIZEOF           EQU 48

WBENCHSCREEN        EQU 1           ; nw_Type

GUI_MIN_WIDTH       EQU 90
GUI_MIN_HEIGHT      EQU 26

; -----------------------------------------------------------------------------
; struct Window - fields read by the runtime
; -----------------------------------------------------------------------------
WD_LEFTEDGE         EQU 4           ; WORD
WD_TOPEDGE          EQU 6           ; WORD
WD_WIDTH            EQU 8           ; WORD
WD_HEIGHT           EQU 10          ; WORD
WD_MOUSEY           EQU 12          ; WORD  (note the order: Y before X)
WD_MOUSEX           EQU 14          ; WORD
WD_RPORT            EQU 50          ; APTR
WD_BORDERLEFT       EQU 54          ; UBYTE
WD_BORDERTOP        EQU 55          ; UBYTE
WD_BORDERRIGHT      EQU 56          ; UBYTE
WD_BORDERBOTTOM     EQU 57          ; UBYTE
WD_FIRSTGADGET      EQU 62          ; APTR
WD_USERPORT         EQU 86          ; APTR

; -----------------------------------------------------------------------------
; struct Gadget - 44 bytes
; -----------------------------------------------------------------------------
GG_NEXTGADGET       EQU 0           ; APTR
GG_LEFTEDGE         EQU 4           ; WORD
GG_TOPEDGE          EQU 6           ; WORD
GG_WIDTH            EQU 8           ; WORD
GG_HEIGHT           EQU 10          ; WORD
GG_FLAGS            EQU 12          ; UWORD
GG_ACTIVATION       EQU 14          ; UWORD
GG_GADGETTYPE       EQU 16          ; UWORD
GG_GADGETRENDER     EQU 18          ; APTR -> Border
GG_SELECTRENDER     EQU 22          ; APTR
GG_GADGETTEXT       EQU 26          ; APTR -> IntuiText
GG_MUTUALEXCLUDE    EQU 30          ; LONG
GG_SPECIALINFO      EQU 34          ; APTR -> StringInfo
GG_GADGETID         EQU 38          ; UWORD
GG_USERDATA         EQU 40          ; APTR
GG_SIZEOF           EQU 44

; -----------------------------------------------------------------------------
; struct Border - 16 bytes
; -----------------------------------------------------------------------------
BD_LEFTEDGE         EQU 0           ; WORD
BD_TOPEDGE          EQU 2           ; WORD
BD_FRONTPEN         EQU 4           ; UBYTE
BD_BACKPEN          EQU 5           ; UBYTE
BD_DRAWMODE         EQU 6           ; UBYTE
BD_COUNT            EQU 7           ; BYTE
BD_XY               EQU 8           ; APTR -> WORD pairs
BD_NEXTBORDER       EQU 12          ; APTR
BD_SIZEOF           EQU 16

GUI_BORDER_POINTS   EQU 3           ; 3 points per 3D bevel segment
GUI_BORDXY_SIZEOF   EQU 24          ; 2 segments * 3 points * 2 words

; -----------------------------------------------------------------------------
; struct IntuiText - 20 bytes
; -----------------------------------------------------------------------------
IT_FRONTPEN         EQU 0           ; UBYTE
IT_BACKPEN          EQU 1           ; UBYTE
IT_DRAWMODE         EQU 2           ; UBYTE
IT_PAD              EQU 3           ; BYTE
IT_LEFTEDGE         EQU 4           ; WORD
IT_TOPEDGE          EQU 6           ; WORD
IT_ITEXTFONT        EQU 8           ; APTR
IT_ITEXT            EQU 12          ; APTR
IT_NEXTTEXT         EQU 16          ; APTR
IT_SIZEOF           EQU 20

; -----------------------------------------------------------------------------
; struct StringInfo - 36 bytes
; -----------------------------------------------------------------------------
SI_BUFFER           EQU 0           ; APTR
SI_UNDOBUFFER       EQU 4           ; APTR
SI_BUFFERPOS        EQU 8           ; WORD
SI_MAXCHARS         EQU 10          ; WORD (includes the terminating NUL)
SI_DISPPOS          EQU 12          ; WORD
SI_UNDOPOS          EQU 14          ; WORD
SI_NUMCHARS         EQU 16          ; WORD
SI_DISPCOUNT        EQU 18          ; WORD
SI_CLEFT            EQU 20          ; WORD
SI_CTOP             EQU 22          ; WORD
SI_EXTENSION        EQU 24          ; APTR
SI_LONGINT          EQU 28          ; LONG
SI_ALTKEYMAP        EQU 32          ; APTR
SI_SIZEOF           EQU 36

; -----------------------------------------------------------------------------
; struct IntuiMessage - 52 bytes
; -----------------------------------------------------------------------------
IM_EXECMESSAGE      EQU 0           ; struct Message, 20 bytes
IM_CLASS            EQU 20          ; ULONG
IM_CODE             EQU 24          ; UWORD
IM_QUALIFIER        EQU 26          ; UWORD
IM_IADDRESS         EQU 28          ; APTR (Gadget* for GADGETUP/GADGETDOWN)
IM_MOUSEX           EQU 32          ; WORD
IM_MOUSEY           EQU 34          ; WORD
IM_SECONDS          EQU 36          ; ULONG
IM_MICROS           EQU 40          ; ULONG
IM_SIZEOF           EQU 52

; -----------------------------------------------------------------------------
; IDCMP flags
; -----------------------------------------------------------------------------
IDCMP_SIZEVERIFY    EQU $00000001
IDCMP_NEWSIZE       EQU $00000002
IDCMP_REFRESHWINDOW EQU $00000004
IDCMP_MOUSEBUTTONS  EQU $00000008
IDCMP_MOUSEMOVE     EQU $00000010
IDCMP_GADGETDOWN    EQU $00000020
IDCMP_GADGETUP      EQU $00000040
IDCMP_MENUPICK      EQU $00000100
IDCMP_CLOSEWINDOW   EQU $00000200
IDCMP_RAWKEY        EQU $00000400
IDCMP_VANILLAKEY    EQU $00200000
IDCMP_INTUITICKS    EQU $00400000

; Bit numbers used by the btst decode chain in GuiWaitEvent
IDCMPB_REFRESHWINDOW EQU 2
IDCMPB_MOUSEBUTTONS  EQU 3
IDCMPB_GADGETDOWN    EQU 5
IDCMPB_GADGETUP      EQU 6
IDCMPB_CLOSEWINDOW   EQU 9
IDCMPB_VANILLAKEY    EQU 21

GUI_IDCMP_DEFAULT   EQU $0020026C   ; CLOSEWINDOW|GADGETUP|GADGETDOWN|
                                    ; MOUSEBUTTONS|VANILLAKEY|REFRESHWINDOW

; im_Code values for IDCMP_MOUSEBUTTONS
GUI_SELECTDOWN      EQU $68
GUI_SELECTUP        EQU $E8
GUI_MENUDOWN        EQU $69
GUI_MENUUP          EQU $E9

; -----------------------------------------------------------------------------
; Window flags
; -----------------------------------------------------------------------------
WFLG_SIZEGADGET     EQU $00000001
WFLG_DRAGBAR        EQU $00000002
WFLG_DEPTHGADGET    EQU $00000004
WFLG_CLOSEGADGET    EQU $00000008
WFLG_SIZEBRIGHT     EQU $00000010
WFLG_SIZEBBOTTOM    EQU $00000020
WFLG_SMART_REFRESH  EQU $00000000   ; ZERO - never OR in $40 by mistake
WFLG_SIMPLE_REFRESH EQU $00000040
WFLG_GIMMEZEROZERO  EQU $00000400   ; deliberately unused by this runtime
WFLG_ACTIVATE       EQU $00001000
WFLG_NOCAREREFRESH  EQU $00020000

GUI_WFLG_DEFAULT    EQU $0000100E   ; DRAGBAR|DEPTHGADGET|CLOSEGADGET|ACTIVATE
GUI_WFLG_SIZEABLE   EQU $0000103F

; -----------------------------------------------------------------------------
; Gadget types / activation / flags
; -----------------------------------------------------------------------------
GTYP_BOOLGADGET     EQU $0001
GTYP_PROPGADGET     EQU $0003
GTYP_STRGADGET      EQU $0004
GTYP_GTYPEMASK      EQU $0007

GACT_RELVERIFY      EQU $0001
GACT_IMMEDIATE      EQU $0002
GACT_TOGGLESELECT   EQU $0100
GACT_STRINGCENTER   EQU $0200
GACT_STRINGRIGHT    EQU $0400
GACT_LONGINT        EQU $0800

GFLG_GADGHCOMP      EQU $0000
GFLG_GADGHBOX       EQU $0001
GFLG_GADGHNONE      EQU $0003
GFLG_GADGIMAGE      EQU $0004
GFLG_SELECTED       EQU $0080
GFLG_DISABLED       EQU $0100
GFLG_TABCYCLE       EQU $0200       ; V36+

; -----------------------------------------------------------------------------
; graphics draw modes
; -----------------------------------------------------------------------------
JAM1                EQU 0
JAM2                EQU 1
COMPLEMENT          EQU 2
INVERSVID           EQU 4

; -----------------------------------------------------------------------------
; Event class codes returned by GuiWaitEvent()
; -----------------------------------------------------------------------------
GUI_EVT_NONE        EQU 0
GUI_EVT_CLOSE       EQU 1
GUI_EVT_BUTTON      EQU 2
GUI_EVT_PRESS       EQU 3
GUI_EVT_STRING      EQU 4
GUI_EVT_KEY         EQU 5
GUI_EVT_MOUSE       EQU 6
GUI_EVT_REFRESH     EQU 7

; -----------------------------------------------------------------------------
; Static pool sizes (section 4.4)
; -----------------------------------------------------------------------------
GUI_MAX_GADGETS     EQU 32
GUI_MAX_LABELS      EQU 32

; Fixed metrics of topaz.font 8, used for caption centring
GUI_FONT_WIDTH      EQU 8
GUI_FONT_HEIGHT     EQU 8

    endc
