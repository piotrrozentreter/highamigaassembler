# GUI Creator

GUI Creator is the initial foundation for a broader Amiga GUI utility. Today it is a WYSIWYG
designer for Amiga forms. It is **not** a standalone application and produces no executable of
its own: it is an editor that emits structured metadata for the HAS/68000 pipeline.

- **Tool:** `guicreator/` (Python 3.8+, Tkinter, no extra dependencies)
- **Layout output:** `.hasmeta` — structured pseudo-code, also the designer's project format
- **Code output:** `.has` — a compilable, system-friendly `intuition.library` program skeleton
- **Runtime contract:** [GUI_INTUITION_RUNTIME_SPEC.md](GUI_INTUITION_RUNTIME_SPEC.md)

```
 designer canvas ──▶ MetadataManager ──▶ form.hasmeta ──▶ form.has ──▶ hasc ──▶ .s ──▶ vasm/vlink
                                                             │
                                                  lib/gui_intuition.s
```

---

## 1. Usage

```bash
# Launch the designer
python -m guicreator

# Launch with a layout loaded
python -m guicreator guicreator/examples/login.hasmeta

# Headless: regenerate the HAS skeleton from a layout
python -m guicreator --export-has guicreator/examples/login.hasmeta -o examples/gui_login_form.has

# Headless: check a layout without opening a window
python -m guicreator --validate guicreator/examples/login.hasmeta
```

Then compile as usual:

```bash
python -m hasc.cli examples/gui_login_form.has -o build/gui_login_form.s
vasmm68k_mot -Fhunk -I lib/ -o build/gui_login_form.o build/gui_login_form.s
vasmm68k_mot -Fhunk -I lib/ -o build/gui_intuition.o  lib/gui_intuition.s
vasmm68k_mot -Fhunk -I lib/ -o build/wbstartup.o      lib/wbstartup.s
vlink -bamigahunk build/gui_login_form.o build/gui_intuition.o build/wbstartup.o \
    -o build/gui_login_form.exe
```

### Designer

| Area | Purpose |
| --- | --- |
| Toolbox | Add Button / CheckBox / EditBox / Label / List / Bitmap |
| Window | Caption, Width, Height, screen position |
| Window flags | `WFLG_DRAGBAR` / `DEPTHGADGET` / `CLOSEGADGET` / `ACTIVATE` / `SIZEGADGET` |
| Canvas | Click to select, drag to move, drag the corner handle to resize, arrows to nudge |
| TAB order | List order = Intuition gadget list order = hit-test priority and TAB cycle |
| Properties | Symbol name, caption/text, X/Y/W/H; MaxLen (EditBox); checked state (CheckBox); `|`-separated items and selected row (List); PNG/BMP asset path and colour count (Bitmap) |
| Validation | Live problem list; export warns before writing an invalid layout |

The dashed rectangle on the canvas is the **client area**. Widgets must stay inside it: window
coordinates start at the outer top-left, so `(0,0)` is underneath the drag bar.

### File menu

- **Save `.hasmeta`** — the project. Round-trips exactly; safe to keep under version control.
- **Export `.has`** — regenerates the skeleton. Anything you wrote between
  `// USER CODE BEGIN <key>` and `// USER CODE END <key>` in the previous file is carried over,
  so handler bodies survive re-export.

---

## 2. Output format

### 2.1 `.hasmeta`

```
; --- METADATA HEADER ---
DEFINE_WINDOW Caption="Login" WIDTH=320 HEIGHT=120 LEFT=40 TOP=30 FLAGS=$0000100E IDCMP=$0020026C

BEGIN_GUI_LAYOUT
    {CALL_HAS_CMD: ADD_CONTROL(TYPE=LABEL, ID=1, X=12, Y=24, W=40, H=8, NAME="lbl_name", TEXT="Name:")}
    {CALL_HAS_CMD: ADD_CONTROL(TYPE=EDITBOX, ID=2, X=92, Y=22, W=200, H=14, NAME="edit_name", ITEXT="", MAXLEN=32)}
    {CALL_HAS_CMD: ADD_CONTROL(TYPE=BUTTON, ID=3, X=116, Y=64, W=88, H=18, NAME="btn_ok", CAPT="OK")}
    {CALL_HAS_CMD: ADD_CONTROL(TYPE=CHECKBOX, ID=4, X=12, Y=64, W=88, H=14, NAME="chk_remember", CAPT="Remember", CHECKED=1)}
    {CALL_HAS_CMD: ADD_CONTROL(TYPE=LIST, ID=5, X=12, Y=88, W=120, H=28, NAME="list_mode", ITEMS64="RWFzeQBIYXJk", SELECTED=0)}
    {CALL_HAS_CMD: ADD_CONTROL(TYPE=BITMAP, ID=6, X=160, Y=88, W=32, H=32, NAME="bmp_logo", ASSET="assets/logo.png", COLORS=16)}
END_GUI_LAYOUT

; --- EVENT HANDLER DEFINITIONS ---
DEFINE_EVENT_HANDLERS START_MODULE
    HANDLE_ACTION(ID: 2, ACTION: EDITBOX_CHANGE): PROCESS_INPUT(memory_offset=edit_name_buf, max_chars=32);
    HANDLE_ACTION(ID: 3, ACTION: BUTTON_CLICK): CALL_FUNCTION(amiga_button_action_3);
    HANDLE_ACTION(ID: 0, ACTION: WINDOW_CLOSE): CALL_FUNCTION(amiga_window_close);
END_EVENT_HANDLERS

; --- CONSTANTS/LAYOUT DATA (For Assembler Consumption) ---
SECTION DATA CONSTANTS
    WINDOW_CAPTION        EQU "Login"
    WINDOW_WIDTH          EQU 320
    ...
    CONTROL_TYPE_LABEL    EQU 0
    CONTROL_TYPE_BUTTON   EQU 1
    CONTROL_TYPE_EDITBOX  EQU 2
    CONTROL_TYPE_CHECKBOX EQU 3
    CONTROL_TYPE_LIST     EQU 4
    CONTROL_TYPE_BITMAP   EQU 5
    ID_LBL_NAME           EQU 1
    ID_EDIT_NAME          EQU 2
    ID_BTN_OK             EQU 3
    EDIT_NAME_MAXLEN      EQU 32
END_SECTION
```

### 2.2 `.has`

See [examples/gui_login_form.has](../examples/gui_login_form.has) and section 7 of the runtime spec.

---

## 3. Technical commentary: metadata → assembler

This is the mapping the implementer of `lib/gui_intuition.s` and any future direct consumer of
`.hasmeta` must honour.

### 3.1 `DEFINE_WINDOW` → `OpenWindow()`

| Metadata | HAS constant | `NewWindow` field | Offset | Size |
| --- | --- | --- | --- | --- |
| `LEFT` | `WIN_X` | `nw_LeftEdge` | 0 | WORD |
| `TOP` | `WIN_Y` | `nw_TopEdge` | 2 | WORD |
| `WIDTH` | `WIN_W` | `nw_Width` | 4 | WORD |
| `HEIGHT` | `WIN_H` | `nw_Height` | 6 | WORD |
| `IDCMP` | `FORM_IDCMP` | `nw_IDCMPFlags` | 10 | LONG |
| `FLAGS` | `FORM_FLAGS` | `nw_Flags` | 14 | LONG |
| *(gadget list)* | — | `nw_FirstGadget` | 18 | APTR |
| `Caption` | `win_title` (`data` section) | `nw_Title` | 26 | APTR |

`DEFINE_WINDOW` is therefore a simulation of exactly one Amiga API call:
`intuition.library/OpenWindow()` (LVO `-204`, `a0` = `NewWindow*`, returns `Window*` in `d0`),
preceded by `exec/OpenLibrary("intuition.library", 37)` (LVO `-552`).

### 3.2 `ADD_CONTROL` → `Gadget` / `IntuiText`

Every control's `X, Y, W, H` become four consecutive WORDs at `Gadget+4`, and `ID` becomes the
UWORD at `Gadget+38`:

| Metadata | `Gadget` field | Offset | Size |
| --- | --- | --- | --- |
| `X` | `gg_LeftEdge` | 4 | WORD |
| `Y` | `gg_TopEdge` | 6 | WORD |
| `W` | `gg_Width` | 8 | WORD |
| `H` | `gg_Height` | 10 | WORD |
| `TYPE` | `gg_GadgetType` | 16 | UWORD |
| `ID` | `gg_GadgetID` | 38 | UWORD |

`TYPE` maps as:

| `.hasmeta` | `CONTROL_TYPE_*` | Intuition | `gg_GadgetType` | Rendered by |
| --- | --- | --- | --- | --- |
| `LABEL` | 0 | *(not a gadget)* | — | `PrintIText()` LVO -216 |
| `BUTTON` | 1 | `GTYP_BOOLGADGET` | `$0001` | `OpenWindow` / `RefreshGList` LVO -432 |
| `EDITBOX` | 2 | `GTYP_STRGADGET` | `$0004` | `OpenWindow` / `RefreshGList` |
| `CHECKBOX` | 3 | `GTYP_BOOLGADGET` | `$0001` | Intuition toggle-select gadget |
| `LIST` | 4 | `GTYP_BOOLGADGET` | `$0001` | Runtime-drawn fixed Topaz-8 rows |
| `BITMAP` | 5 | `GTYP_BOOLGADGET` | `$0001` | Intuition `Image` gadget; no generated event handler |

Coordinate caveats the metadata deliberately hides from the designer:

- **Buttons:** `X,Y,W,H` are the select box directly. The auto-generated `Border` polyline is
  `0,0 → W-1,0 → W-1,H-1 → 0,H-1 → 0,0` (5 points; Intuition does not auto-close a polyline).
- **EditBoxes:** the designer's rectangle is the *outer frame*, but a string gadget's
  `LeftEdge/TopEdge/Width/Height` describe the *text area*. `GuiAddEditBox` converts:
  `LeftEdge = X+2, TopEdge = Y+2, Width = W-4, Height = H-4`, and the `Border` uses negative
  offsets so the frame surrounds the text.
- **Labels:** `X,Y` are passed to `PrintIText()` as the `d0`/`d1` draw offsets; `W,H` are advisory
  and used only by the designer's hit-testing and overlap check.
- **CheckBoxes:** `CHECKED=0`/`1` supplies the initial state. Intuition owns the selected flag;
  generated `on_checkbox()` handlers read it with `GuiGetCheckBox()`.
- **Lists:** `ITEMS64` is a base64-encoded, NUL-separated string list and `SELECTED` is a zero-based initial row.
  Clicking a visible row changes the selection and emits an event. Lists are intentionally
  single-select, fixed-row controls: there is no scrolling or multiselect behavior.
- **Bitmaps:** `ASSET` must name a PNG or BMP. `COLORS` may be `2`, `8`, `16`, or `32`, mapping
  to 1, 3, 4, or 5 Intuition `Image` bitplanes. Export requires Pillow, resizes the source to
  the control's `W,H` using nearest-neighbor sampling, and Floyd-Steinberg dithers it to the
  selected indexed depth. Transparent pixels become pen 0. The exported `Image` uses Workbench
  screen pens; it does not install a private palette, so the visible colours depend on the
  Workbench screen depth and palette. The exporter generates no bitmap handler; bitmap
  `GADGETUP` events are ignored by the runtime.
- **All coordinates are window-relative**, i.e. `(0,0)` is under the drag bar. `WFLG_GIMMEZEROZERO`
  is deliberately not used, so the canvas origin is pre-inset by `(4, 11)`.

### 3.3 `HANDLE_ACTION` → the IDCMP dispatch

The `ActionID` is the only thing that survives into the running program as an identity. The chain
is:

```
designer ActionID  →  ID_* EQU / const  →  gg_GadgetID (Gadget+38)
                                              ▲
IntuiMessage.im_IAddress (offset 28) ──────────┘
IntuiMessage.im_Class    (offset 20)  →  GUI_EVT_* → on_button()/on_string()
```

| `.hasmeta` action | IDCMP class | Bit | Generated handler |
| --- | --- | --- | --- |
| `BUTTON_CLICK` | `IDCMP_GADGETUP` | `$40` | `proc on_button(id)` |
| `EDITBOX_CHANGE` | `IDCMP_GADGETUP` on `GTYP_STRGADGET` | `$40` | `proc on_string(id)` |
| `CHECKBOX_CHANGE` | `IDCMP_GADGETUP` on a checkbox | `$40` | `proc on_checkbox(id)` |
| `LIST_SELECT` | `IDCMP_GADGETUP` on a list row | `$40` | `proc on_list(id)` |
| `WINDOW_CLOSE` | `IDCMP_CLOSEWINDOW` | `$200` | `proc on_close()` |
| *(implicit)* | `IDCMP_VANILLAKEY` | `$200000` | `proc on_key(code)` |
| *(implicit)* | `IDCMP_REFRESHWINDOW` | `$04` | handled inside `GuiWaitEvent()` |

`PROCESS_INPUT(memory_offset=NAME_buf, max_chars=N)` maps to the `StringInfo` at `Gadget+34`:
`si_Buffer` = `&NAME_buf`, `si_UndoBuffer` = `&NAME_undo`, `si_MaxChars` = `N`. `max_chars`
**includes the terminating NUL**, so a 31-character field is `MAXLEN=32`.

### 3.4 Amiga API calls the compiled program executes

In order, for the lifetime of a generated form:

| Phase | Call | LVO | Library |
| --- | --- | --- | --- |
| startup | `WBStartup` handshake (`pr_CLI` probe, `WaitPort`/`GetMsg`) | — | `lib/wbstartup.s` |
| `GuiInit` | `OpenLibrary("intuition.library", 37)` | -552 | exec |
| `GuiInit` | `OpenLibrary("graphics.library", 37)` | -552 | exec |
| `GuiShow` | `OpenWindow(NewWindow*)` | -204 | intuition |
| `GuiShow` | `PrintIText()` per label | -216 | intuition |
| loop | `Wait(1 << UserPort->mp_SigBit)` | -318 | exec |
| loop | `GetMsg(UserPort)` | -372 | exec |
| loop | `ReplyMsg(msg)` | -378 | exec |
| refresh | `BeginRefresh` / `EndRefresh` | -354 / -366 | intuition |
| updates | `RefreshGList` / `ActivateGadget` | -432 / -462 | intuition |
| close | `Forbid` / `ModifyIDCMP(win,0)` / drain / `RemoveGList` / `CloseWindow` / `Permit` | -132 / -150 / -444 / -72 / -138 | exec + intuition |
| `GuiShutdown` | `CloseLibrary(graphics)` then `CloseLibrary(intuition)` | -414 | exec |

### 3.5 Memory placement

Almost everything the generator emits is CPU-accessed only, so it goes in plain fast RAM. The
one exception is **bitmap pixel data**: `intuition.library/DrawImage` renders a `struct Image`
through the **blitter**, which can only read **chip RAM**, so the pixel data must be `data_chip`.

| Emitted | Section | Why |
| --- | --- | --- |
| Window title, label texts, button/check box captions, list item strings | `data` | read-only, must outlive the window |
| List pointer tables and `struct Image` headers | inline `asm` after generated procedures | address-bearing static data; CPU-accessed only, never at the code entry point |
| Bitmap pixel data (`*_image_data`) | `data_chip` | `DrawImage` reads it via the blitter — fast RAM renders as garbage/stripes |
| `NAME_buf`, `NAME_undo` | `bss` | `si_Buffer`/`si_UndoBuffer` must be **writable** |
| `Gadget`/`Border`/`IntuiText`/`StringInfo` pools | `bss` (in `lib/gui_intuition.s`) | static, no `AllocMem` |

Only bitmap pixel data uses chip RAM. The `struct Image` header, gadget pools, strings and
buffers all stay in fast RAM.

---

## 4. Validation rules

`MetadataManager.validate()` runs live in the designer and in `--validate`/`--export-has`:

1. Window at least 90 × 26 (Intuition's floor for a window with system gadgets).
2. Non-empty window caption.
3. At most `GUI_MAX_GADGETS` (32) gadget controls (Button, EditBox, CheckBox, List, Bitmap) and
  `GUI_MAX_LABELS` (32) labels.
4. ActionIDs unique and ≥ 1 (0 is reserved for "no gadget").
5. Control names unique and valid HAS identifiers (they become assembler symbols).
6. Every control rectangle inside the client area.
7. No two controls overlap — Intuition hit-testing takes the first list match, so overlap is
   always a layout bug.
8. EditBox `maxlen` ≥ 2 and wide enough for one character.
9. A List has at least one item, its selected row is in range, and it is at least one text row
  high.
10. A Bitmap has a PNG or BMP asset path. Export also requires Pillow to read and convert it.

ActionIDs are **never recycled** when a control is deleted, so IDs stay stable across
regeneration and hand-written handler bodies keep referring to the right widget.

---

## 5. Implementation phases

| Phase | Deliverable | Where |
| --- | --- | --- |
| 1 — Data architecture & basic GUI | `MetadataManager`, `WindowSpec`, `Control`; `DEFINE_WINDOW` + labels | [guicreator/model.py](../guicreator/model.py) |
| 2 — Interactivity & event handling | Button + EditBox, mandatory `ActionID` counter, `HANDLE_ACTION` emission | [guicreator/hasmeta.py](../guicreator/hasmeta.py) |
| 3 — Finalisation | `.hasmeta` export, `.has` skeleton, technical commentary | [guicreator/has_export.py](../guicreator/has_export.py), this document |
